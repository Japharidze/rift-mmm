"""Champion labelling: the plain loop.

No agent framework (CLAUDE.md, frozen decisions). One model call per champion
x role, validated against ChampionLabel, retried a bounded number of times on
a malformed response, written through db.py. This module does not decide how
many sub-traits there are or what they mean -- that is docs/sub-traits.md.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

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

# On claude-opus-5 omitting `thinking` runs adaptive thinking at effort `high`,
# which every run before label_run.effort existed did without saying so. Ten
# bounded scores against a fixed rubric does not need that depth, and output
# tokens are most of what a label costs: the input is ~3.5k tokens, 91% of it
# the cached prefix. Low is the starting point, not a measured optimum -- grade
# the first low-effort run with `r3m check-anchors` before trusting it, the
# same as a prompt change.
DEFAULT_EFFORT = "low"

# Room for thinking plus the tool call. The old 1024 was shared with thinking,
# and a long pass could end the response before the tool_use block arrived --
# which read as a malformed answer, not a truncated one. Billing is by tokens
# generated, so the ceiling costs nothing unless it is used.
MAX_TOKENS = 16000

MAX_ATTEMPTS = 3

# Transport retries (429, 5xx, dropped connections), below MAX_ATTEMPTS. The
# SDK default is 2; label_run 9 lost 8 rows to network errors at that.
MAX_RETRIES = 5


# List prices per million tokens (Anthropic, 2026) -- for reporting what a run
# cost, not for billing. Cache writes are the 5-minute TTL rate (1.25x input),
# reads 0.1x. Check against the pricing page before quoting a number.
PRICES = {
    "claude-opus-5": {"input": 5.00, "output": 25.00, "cache_write": 6.25, "cache_read": 0.50},
    # Verified on the pricing page 2026-09-29. Cache reads are 0.05x input on
    # this model, not the usual 0.1x -- the rate that matters for a prompt that
    # is ~99% cached.
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_write": 5.00, "cache_read": 0.20},
}

# Models that still accept a forced tool call. Opus 5.5 rejects
# tool_choice {"type": "tool"} with a 400 (its migration guide, 2026-09-22), so
# it gets "auto" -- safe here because both system prompts already say "Respond
# only by calling the emit_champion_label tool", so no prompt wording changes
# and v3 / games-v2 stay the validated versions. A reply without the call is
# caught by missing_tool_use and retried. Opus 5 keeps the forced call: that is
# how every validated Opus 5 label was made, and a fallback to it must match.
# Deliberately no server-side `fallbacks`: a refused call answered by another
# model would mix two labelling regimes in one run.
FORCED_TOOL_CHOICE = {"claude-opus-5"}


def tool_choice(model: str) -> dict[str, str]:
    if model in FORCED_TOOL_CHOICE:
        return {"type": "tool", "name": TOOL_NAME}
    return {"type": "auto"}


@dataclass
class Usage:
    """Tokens over a run, every attempt included: a retry is paid for too."""
    calls: int = 0
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0

    def add(self, u: Any) -> None:
        self.calls += 1
        self.input += u.input_tokens
        self.output += u.output_tokens
        self.cache_write += getattr(u, "cache_creation_input_tokens", 0) or 0
        self.cache_read += getattr(u, "cache_read_input_tokens", 0) or 0

    def dollars(self, model: str) -> float | None:
        p = PRICES.get(model)
        if p is None:
            return None
        return (self.input * p["input"] + self.output * p["output"]
                + self.cache_write * p["cache_write"] + self.cache_read * p["cache_read"]) / 1e6


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
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=MAX_RETRIES)


def missing_tool_use(response: anthropic.types.Message) -> RuntimeError:
    """Say why there was no tool call, so a truncation is not read as noise."""
    u = response.usage
    return RuntimeError(
        f"no tool_use block in the response (stop_reason={response.stop_reason}, "
        f"output_tokens={u.output_tokens})"
    )


def _call(
    client: anthropic.Anthropic,
    *,
    model: str,
    effort: str,
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
            max_tokens=MAX_TOKENS,
            output_config={"effort": effort},
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
            tool_choice=tool_choice(model),
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
            last_error = missing_tool_use(response)
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
    effort: str = DEFAULT_EFFORT,
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
                    effort=effort,
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
                    conn, prompt_version=PROMPT_VERSION, model=model, effort=effort,
                    note=note,
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
