"""HTTP layer over the quiz.

Thin on purpose: every endpoint is a call into r3m, which is where the
behaviour and its reasoning live. If something here grows a rule of its own —
how to aggregate picks, when a dimension counts as read, what makes a match
close — it belongs in the package instead, or it becomes a second place the
rule exists and the two drift. That has already happened three times in this
project (the bank flag, "which labels are current", the exclusion list), so it
is worth being blunt about.
"""

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from r3m import db, quiz

app = FastAPI(title="r3m", version="0.1.0")

# The dev frontend runs on a different port, so the browser needs permission.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _games() -> list[dict[str, Any]]:
    with db.connect() as conn:
        return db.game_points(conn)


class Game(BaseModel):
    id: str
    name: str
    mode: str | None = None


class NextRequest(BaseModel):
    served: list[str] = Field(default_factory=list)
    picked: list[str] = Field(default_factory=list)


class NextResponse(BaseModel):
    # None means stop: either every dimension is read or the budget is spent.
    item: Game | None
    asked: int


class Dimension(BaseModel):
    value: float
    informative: int
    read: bool


class Match(BaseModel):
    champion_id: str
    name: str
    role: str
    distance: float
    confidence: str


class ResultRequest(BaseModel):
    picked: list[str]
    n: int = 5


class Result(BaseModel):
    point: list[float]
    dimensions: dict[str, Dimension]
    champions: list[Match]
    unknown: list[str]
    # Only populated for dimensions the picks could not read. Reporting the gap
    # and offering a way to close it is a frozen decision (CLAUDE.md): never
    # impute the middle.
    unread: dict[str, list[Game]]


@app.get("/games", response_model=list[Game])
def games() -> list[Game]:
    return [
        Game(id=g["game_id"], name=g["name"], mode=g["mode"])
        for g in _games()
        if g["in_bank"]
    ]


@app.post("/quiz/next", response_model=NextResponse)
def next_item(req: NextRequest) -> NextResponse:
    item = quiz.next_item(req.served, req.picked, _games())
    return NextResponse(
        item=None if item is None
        else Game(id=item["game_id"], name=item["name"], mode=item["mode"]),
        asked=len(req.served),
    )


@app.post("/quiz/result", response_model=Result)
def result(req: ResultRequest) -> Result:
    rows = _games()
    try:
        est = quiz.estimate(req.picked, rows=rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Result(
        point=list(est.point),
        dimensions={
            d: Dimension(value=e.value, informative=e.informative, read=e.read)
            for d, e in est.dimensions.items()
        },
        champions=[
            Match(champion_id=m.champion_id, name=m.name, role=m.role,
                  distance=round(m.distance, 3), confidence=m.confidence)
            for m in quiz.champions_for(est, n=req.n)
        ],
        unknown=est.unknown,
        unread={
            d: [
                Game(id=g["game_id"], name=g["name"], mode=g["mode"])
                for g in quiz.suggest_for(
                    d, exclude=[p["game_id"] for p in est.picked], rows=rows, n=4
                )
            ]
            for d in est.unread
        },
    )
