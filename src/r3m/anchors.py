"""The anchor regression test.

anchors/champions.yaml holds hand-set MMM scores for a handful of champions.
A labelling run that lands outside those bands means the prompt or the model
changed, not the game (CLAUDE.md, Conventions).

Only `tight` scores can fail a run. `wide` means the scores are Sergi's but the
champion is one he has not played; `provisional` means a model placed or moved
them, and a model-set anchor cannot test a model -- agreement between two
models is not evidence. Both are reported and neither blocks.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from r3m import db
from r3m.config import ANCHORS_FILE

DIMENSIONS = ("micro", "meso", "macro")
BLOCKING_TIER = "tight"


@dataclass(frozen=True)
class Comparison:
    champion_id: str
    dimension: str
    label: float
    low: float
    high: float
    tier: str

    @property
    def inside(self) -> bool:
        return self.low <= self.label <= self.high

    @property
    def blocking(self) -> bool:
        return self.tier == BLOCKING_TIER and not self.inside

    @property
    def drift(self) -> float:
        """Signed distance outside the band; 0.0 when inside it."""
        if self.inside:
            return 0.0
        return self.label - self.high if self.label > self.high else self.label - self.low


@dataclass(frozen=True)
class CheckResult:
    label_run_id: int
    prompt_version: str
    model: str
    comparisons: list[Comparison]
    unlabelled: list[str]   # anchors the run did not cover

    @property
    def failures(self) -> list[Comparison]:
        return [c for c in self.comparisons if c.blocking]

    @property
    def misses(self) -> list[Comparison]:
        """Outside the band, but not blocking."""
        return [c for c in self.comparisons if not c.inside and not c.blocking]


def load(path: Path = ANCHORS_FILE) -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(path.read_text())
    return {entry["id"]: entry for entry in data["champions"]}


def check(label_run_id: int | None = None, path: Path = ANCHORS_FILE) -> CheckResult:
    anchors = load(path)

    with db.connect() as conn:
        run_id = label_run_id or db.latest_label_run(conn)
        if run_id is None:
            raise RuntimeError("no labelling run has produced any labels yet")
        scores = db.label_run_scores(conn, run_id)

    if not scores:
        raise RuntimeError(f"label_run {run_id} has no labels")

    labelled = {s["champion_id"]: s for s in scores}
    comparisons = [
        Comparison(
            champion_id=cid,
            dimension=dim,
            label=labelled[cid][dim],
            low=anchors[cid][dim]["band"][0],
            high=anchors[cid][dim]["band"][1],
            tier=anchors[cid][dim]["tier"],
        )
        for cid in sorted(anchors)
        if cid in labelled
        for dim in DIMENSIONS
    ]

    return CheckResult(
        label_run_id=run_id,
        prompt_version=scores[0]["prompt_version"],
        model=scores[0]["model"],
        comparisons=comparisons,
        unlabelled=sorted(cid for cid in anchors if cid not in labelled),
    )
