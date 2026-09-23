"""Game labelling: the same plain loop as champions, different subject.

Deliberately a near-copy of r3m.labeling.run rather than a generalisation of
it. The two will diverge — games have no kit_text, no role, and will grow a
quiz bank the champion side has no equivalent of — and a shared abstraction
built before that divergence is visible tends to be the wrong one.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from r3m import db
from r3m.labeling.game_prompt import (
    GAME_PROMPT_VERSION,
    GAME_SYSTEM_PROMPT,
    build_game_message,
)
from r3m.labeling.run import DEFAULT_MODEL, MAX_ATTEMPTS, LabelFailure, _client
from r3m.labeling.schema import TOOL_SCHEMA, ChampionLabel


@dataclass(frozen=True)
class GameRunResult:
    label_run_id: int | None
    targeted: int
    labelled: int
    failed: list[LabelFailure] = field(default_factory=list)


def _call(client, *, model: str, name: str, mode: str | None):
    last_error: Exception | None = None
    for _ in range(MAX_ATTEMPTS):
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=[{"type": "text", "text": GAME_SYSTEM_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            tools=[TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": TOOL_SCHEMA["name"]},
            messages=[{"role": "user",
                       "content": build_game_message(name=name, mode=mode)}],
        )
        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        if tool_use is None:
            last_error = RuntimeError("no tool_use block in the response")
            continue
        try:
            return ChampionLabel.model_validate(tool_use.input), tool_use.input
        except Exception as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def run(*, model: str = DEFAULT_MODEL, games: Sequence[str] | None = None,
        note: str | None = None) -> GameRunResult:
    client = _client()
    with db.connect() as conn:
        targets = db.game_labelling_targets(conn, game_ids=games)
        if not targets:
            return GameRunResult(label_run_id=None, targeted=0, labelled=0)

        label_run_id: int | None = None
        failed: list[LabelFailure] = []
        labelled = 0

        for t in targets:
            try:
                label, raw = _call(client, model=model, name=t["name"], mode=t["mode"])
            except Exception as exc:
                failed.append(LabelFailure(t["game_id"], t["mode"] or "-", str(exc)))
                continue

            if label_run_id is None:
                label_run_id = db.insert_label_run(
                    conn, prompt_version=GAME_PROMPT_VERSION, model=model, note=note
                )

            fields = label.model_dump(exclude={"rationale"})
            fields["rationale"] = label.rationale
            fields["micro"], fields["meso"], fields["macro"] = (
                label.micro, label.meso, label.macro
            )
            db.insert_game_label(
                conn, label_run_id=label_run_id, game_id=t["game_id"],
                fields=fields, raw_response=raw,
            )
            conn.commit()
            labelled += 1

    return GameRunResult(label_run_id=label_run_id, targeted=len(targets),
                         labelled=labelled, failed=failed)
