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

from pydantic import BaseModel, Field, model_validator


def _score(description: str, *, optional: bool = False) -> float:
    if optional:
        return Field(default=None, ge=0.0, le=1.0, description=description)  # type: ignore[return-value]
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
    # Exactly one of these two is asked for, decided by the prompt version that
    # builds the tool schema. Champions from v10 use macro_resources; game
    # labelling (games-v2) and every champion run before v10 use
    # macro_win_condition. Both are optional here so one model serves both,
    # and the validator below refuses a response carrying neither.
    macro_win_condition: float | None = _score(
        "Does good play mean building toward a specific late-game plan "
        "rather than winning exchanges in isolation?",
        optional=True,
    )
    macro_resources: float | None = _score(
        "Does strength come from managing the map's renewable resources -- "
        "waves, time, denial -- rather than from fighting?",
        optional=True,
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

    @model_validator(mode="after")
    def _one_middle_macro_trait(self) -> "ChampionLabel":
        got = [v for v in (self.macro_win_condition, self.macro_resources) if v is not None]
        if len(got) != 1:
            raise ValueError(
                "exactly one of macro_win_condition / macro_resources is required"
            )
        return self

    @property
    def macro_middle(self) -> float:
        """Whichever of the two the run asked for.

        They occupy the same slot in the aggregate, so a v3 macro and a v10
        macro stay on one scale even though the question changed. That is the
        point of a version: the diff is the finding.
        """
        v = self.macro_win_condition if self.macro_win_condition is not None else self.macro_resources
        assert v is not None
        return v

    @property
    def macro(self) -> float:
        return round(
            (self.macro_routing + self.macro_middle + self.macro_cheat) / 3, 2
        )


TOOL_NAME = "emit_champion_label"

def tool_schema(middle: str = "macro_win_condition") -> dict:
    """The tool schema carrying only the middle macro sub-trait this run wants.

    Offering both would let the model answer whichever question it preferred,
    which is precisely the drift a versioned prompt exists to prevent. The
    unwanted field is removed outright and the wanted one made required, so a
    v10 run cannot silently return a v3 answer.
    """
    schema = ChampionLabel.model_json_schema()
    drop = ("macro_resources" if middle == "macro_win_condition"
            else "macro_win_condition")
    schema["properties"].pop(drop, None)
    required = [r for r in schema.get("required", []) if r != drop]
    if middle not in required:
        required.insert(required.index("macro_routing") + 1, middle)
    schema["required"] = required
    return {
        "name": TOOL_NAME,
        "description": (
            "Emit the ten sub-trait scores and a short rationale for one "
            "champion x role."
        ),
        "input_schema": schema,
    }


# Games (games-v2) and every champion run before v10 ask for win_condition.
TOOL_SCHEMA = tool_schema("macro_win_condition")
