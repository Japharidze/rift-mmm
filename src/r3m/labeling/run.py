"""Champion labelling: the plain loop.

No agent framework (CLAUDE.md, frozen decisions). One model call per champion
x role, validated against ChampionLabel, retried a bounded number of times on
a malformed response, written through db.py. This module does not decide how
many sub-traits there are or what they mean -- that is docs/sub-traits.md.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

import anthropic

from r3m import db
from r3m.config import settings
from r3m.labeling.prompt import (
    MACRO_MIDDLE,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_message,
)
from r3m.labeling.schema import TOOL_NAME, ChampionLabel, tool_schema

# The instructions say to default to the latest, most capable Claude model
# when building an AI application. Overridable per run (a bulk pass over
# ~170 champions may prefer a cheaper model; that is a call for whoever runs
# it, not one to bake in here).
DEFAULT_MODEL = "claude-opus-5"

MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class LabelFailure:
    champion_id: str
    role: str
    error: str


@dataclass(frozen=True)
class LabelRunResult:
    # None when there was nothing to label -- no label_run row gets created
    # for an empty scope, so there is nothing to point this at.
    label_run_id: int | None
    targeted: int
    labelled: int
    failed: list[LabelFailure] = field(default_factory=list)


def _client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to .env before running "
            "r3m label."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _call(
    client: anthropic.Anthropic,
    *,
    model: str,
    champion_name: str,
    title: str,
    role: str,
    kit_text: str,
) -> tuple[ChampionLabel, dict]:
    """One champion x role, retried on a malformed response.

    Retries resend the same request rather than an error message: the
    failures actually seen at this scale are Claude's own tool-schema
    validation catching an out-of-range score or a missing field, and a fresh
    sample clears those. Feeding the error back is complexity the pilot does
    not need yet.
    """
    last_error: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            # 82% of each call is this fixed prefix, identical for every
            # champion. Cached, it costs a tenth on every call after the first.
            # Render order is tools -> system -> messages, so a breakpoint on
            # system covers the tool schema too, and the champion-specific user
            # message stays outside the cached prefix where it belongs.
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            tools=[tool_schema(MACRO_MIDDLE)],
            tool_choice={"type": "tool", "name": TOOL_NAME},
            messages=[
                {
                    "role": "user",
                    "content": build_user_message(
                        champion_name=champion_name,
                        title=title,
                        role=role,
                        kit_text=kit_text,
                    ),
                }
            ],
        )
        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_use is None:
            last_error = RuntimeError("no tool_use block in the response")
            continue
        try:
            label = ChampionLabel.model_validate(tool_use.input)
        except Exception as exc:  # pydantic ValidationError, mainly
            last_error = exc
            continue
        return label, tool_use.input
    assert last_error is not None
    raise last_error


def run(
    *,
    model: str = DEFAULT_MODEL,
    champions: Sequence[str] | None = None,
    note: str | None = None,
) -> LabelRunResult:
    """Label every live champion x role, or just `champions` if given.

    Always a full pass over its scope, never a resume of a partial one: labels
    are append-only per label_run (CLAUDE.md), so a run that stopped halfway
    is not "missing rows to fill in" the way a match crawl is -- it is an
    incomplete run, and the next one is a new run rather than a continuation.

    label_run.started_at is therefore the first successful label, not the
    moment the process began -- close enough to be useful, and the difference
    only shows when early champions fail.
    """
    client = _client()

    with db.connect() as conn:
        targets = db.labelling_targets(conn, champion_ids=champions)
        if not targets:
            # No label_run row for an empty scope -- most likely there is no
            # match sample yet, so champion_role_live has nothing live in it.
            return LabelRunResult(label_run_id=None, targeted=0, labelled=0)

        # Created on the first success, not up front. A run that labels
        # nothing -- an expired key, no credit -- then leaves no row behind, so
        # "the latest run" never means an empty one. A run that labels some and
        # fails the rest still gets its row, because the first success creates
        # it before the failures matter.
        label_run_id: int | None = None
        failed: list[LabelFailure] = []
        labelled = 0
        for target in targets:
            try:
                label, raw = _call(
                    client,
                    model=model,
                    champion_name=target["name"],
                    title=target["title"],
                    role=target["role"],
                    kit_text=target["kit_text"],
                )
            except Exception as exc:
                failed.append(LabelFailure(target["champion_id"], target["role"], str(exc)))
                continue

            if label_run_id is None:
                label_run_id = db.insert_label_run(
                    conn, prompt_version=PROMPT_VERSION, model=model, note=note
                )

            fields = label.model_dump(exclude={"rationale"})
            fields["rationale"] = label.rationale
            fields["micro"] = label.micro
            fields["meso"] = label.meso
            fields["macro"] = label.macro

            db.insert_champion_label(
                conn,
                label_run_id=label_run_id,
                champion_id=target["champion_id"],
                role=target["role"],
                fields=fields,
                raw_response=raw,
            )
            conn.commit()  # per row, so an interrupted run keeps what it labelled
            labelled += 1

    return LabelRunResult(
        label_run_id=label_run_id, targeted=len(targets), labelled=labelled, failed=failed
    )
