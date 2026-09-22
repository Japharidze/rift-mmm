"""Structured-output schema for one champion label.

Field names match docs/sub-traits.md and the champion_label columns in
migrations/006_champion_label.sql exactly, so a row round-trips without a
translation layer.

Aggregates are not asked of the model -- they are computed here as the
equal-weight mean within each dimension (CLAUDE.md, open questions: weights
are equal for the pilot, fit against Surnex's own placements later). An LLM
asked to also do the arithmetic is one more place for the stored aggregate to
drift from what its own sub-trait scores imply.
"""

from pydantic import BaseModel, Field


def _score(description: str) -> float:
    return Field(ge=0.0, le=1.0, description=description)  # type: ignore[return-value]


class ChampionLabel(BaseModel):
    micro_precision: float = _score(
        "Do core abilities require landing skillshots or precise placement, "
        "vs. auto-target or self-cast?"
    )
    micro_execution: float = _score(
        "Does effective use require chaining abilities in a tight timing "
        "window (cancels, resets, combo order)?"
    )
    micro_cheat: float = _score(
        "Would perfect inputs alone make this champion dramatically "
        "stronger?"
    )

    meso_deception: float = _score(
        "Does the kit let the champion disguise intent or threaten falsely?"
    )
    meso_prediction: float = _score(
        "Does the kit force commitment before the enemy has shown what they "
        "will do? Instant and point-and-click abilities are low; slow "
        "projectiles, long casts, zones and traps aimed where the enemy will "
        "be are high."
    )
    meso_exploitation: float = _score(
        "Does power come from reading this specific opponent's habits over "
        "a match, rather than one fixed optimal line?"
    )
    meso_cheat: float = _score(
        "Would knowing the enemy's hidden state before it happens make this "
        "champion dramatically stronger than it would make an average "
        "champion?"
    )

    macro_routing: float = _score(
        "How many decisions about where to be does this champion's player "
        "make, and how much do they change the game? Locked to a lane and "
        "moving when the team moves is low; choosing objectives, abandoning "
        "lanes, or constraining the enemy by presence is high."
    )
    macro_win_condition: float = _score(
        "Does good play mean building toward a specific late-game plan "
        "rather than winning exchanges in isolation?"
    )
    macro_cheat: float = _score(
        "Would a perfect coach, with no mechanical or read improvement, make "
        "this champion dramatically stronger than the same coaching would "
        "make an average champion?"
    )

    rationale: str = Field(
        description="2-4 sentences: why these scores, tied to specific abilities."
    )

    @property
    def micro(self) -> float:
        return round((self.micro_precision + self.micro_execution + self.micro_cheat) / 3, 2)

    @property
    def meso(self) -> float:
        return round(
            (self.meso_deception + self.meso_prediction
             + self.meso_exploitation + self.meso_cheat) / 4,
            2,
        )

    @property
    def macro(self) -> float:
        return round(
            (self.macro_routing + self.macro_win_condition + self.macro_cheat) / 3, 2
        )


TOOL_NAME = "emit_champion_label"

TOOL_SCHEMA = {
    "name": TOOL_NAME,
    "description": (
        "Emit the ten sub-trait scores and a short rationale for one "
        "champion x role."
    ),
    "input_schema": ChampionLabel.model_json_schema(),
}
