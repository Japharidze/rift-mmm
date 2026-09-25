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

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from r3m import db, quiz
from r3m.config import ROOT

app = FastAPI(title="r3m", version="0.1.0")

# Routes live under /api in both environments. Vite used to strip the prefix
# when proxying, which worked only because the frontend and the API were on
# different origins; serving the build from this process makes them one, and
# then the path the browser asks for has to be the path that exists.
api = APIRouter(prefix="/api")

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


# Steam serves this for every app; there is no key and no per-title check
# needed, so a stored appid is enough to render a cover.
STEAM_COVER = "https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"


class Game(BaseModel):
    id: str
    name: str
    mode: str | None = None
    # Both optional and both often absent. Steam covers about half the bank and
    # misses the Nintendo, Blizzard, Riot and mobile titles; series entries
    # (Tekken, Mario Kart) have no single year. The client renders a card
    # without art as a typographic card, not as a broken one.
    cover_url: str | None = None
    year: int | None = None


def _to_game(g: dict[str, Any]) -> Game:
    appid = g.get("steam_appid")
    return Game(
        id=g["game_id"],
        name=g["name"],
        mode=g["mode"],
        cover_url=STEAM_COVER.format(appid=appid) if appid else None,
        year=g.get("release_year"),
    )


class NextRequest(BaseModel):
    served: list[str] = Field(default_factory=list)
    loved: list[str] = Field(default_factory=list)
    disliked: list[str] = Field(default_factory=list)


class NextResponse(BaseModel):
    # None means stop: either every dimension is read or the budget is spent.
    item: Game | None
    asked: int


class Dimension(BaseModel):
    value: float
    # Weighted, so fractional: a disliked game counts half (quiz.DISLIKE_WEIGHT).
    informative: float
    read: bool
    label: str
    gloss: str


class Match(BaseModel):
    champion_id: str
    name: str
    role: str
    distance: float
    confidence: str
    # None when no dimension is both decided and shared — an absent reason
    # beats a manufactured one.
    because: str | None = None


class Comparison(BaseModel):
    winner: str
    loser: str
    # The dimension the pair isolates. Sent back so the server does not have to
    # re-derive which axis a pair was offered for.
    dimension: str


class ResultRequest(BaseModel):
    loved: list[str]
    disliked: list[str] = Field(default_factory=list)
    n: int = 5
    # Stage 3. Empty on the provisional result, which is a complete answer on
    # its own -- refinement is offered after it, never required before it.
    comparisons: list[Comparison] = Field(default_factory=list)


class FillRequest(BaseModel):
    served: list[str] = Field(default_factory=list)
    loved: list[str] = Field(default_factory=list)
    disliked: list[str] = Field(default_factory=list)
    asked: int = 0


class EstimateRequest(BaseModel):
    loved: list[str] = Field(default_factory=list)
    disliked: list[str] = Field(default_factory=list)


class EstimateResponse(BaseModel):
    dimensions: dict[str, Dimension]


class SharpenRequest(BaseModel):
    loved: list[str]
    disliked: list[str] = Field(default_factory=list)
    used: list[str] = Field(default_factory=list)
    # Answers already folded in. Without them this endpoint picks the next axis
    # from where the player was before the first comparison, while /quiz/result
    # reports where they are after it -- the two then disagree about the point,
    # and the second question is chosen for a position nobody is at any more.
    comparisons: list[Comparison] = Field(default_factory=list)


class SharpenResponse(BaseModel):
    # None when nothing in the loved set isolates an axis worth asking about.
    # Stage 3 degrades by disappearing (docs/quiz-flow.md).
    dimension: str | None = None
    label: str | None = None
    gloss: str | None = None
    pair: list[Game] = Field(default_factory=list)
    # Worded here because only the server knows what the two games were
    # answered as. "Which did you like more" is nonsense about two games
    # somebody bounced off, and pairs now come from everything recognised.
    question: str | None = None


class Result(BaseModel):
    point: list[float]
    dimensions: dict[str, Dimension]
    champions: list[Match]
    unknown: list[str]
    # Only populated for dimensions the picks could not read. Reporting the gap
    # and offering a way to close it is a frozen decision (CLAUDE.md): never
    # impute the middle.
    unread: dict[str, list[Game]]


@api.get("/games", response_model=list[Game])
def games() -> list[Game]:
    return [_to_game(g) for g in _games() if g["in_bank"]]


def _dimensions(est: quiz.Estimate) -> dict[str, Dimension]:
    return {
        d: Dimension(value=e.value, informative=e.informative, read=e.read,
                     label=quiz.LABELS[d][0], gloss=quiz.LABELS[d][1])
        for d, e in est.dimensions.items()
    }


@api.get("/quiz/grid", response_model=list[Game])
def quiz_grid() -> list[Game]:
    """Stage 1: the whole opening screen in one call."""
    return [_to_game(g) for g in quiz.grid(_games())]


@api.post("/quiz/estimate", response_model=EstimateResponse)
def quiz_estimate(req: EstimateRequest) -> EstimateResponse:
    """The running point, for the live readout.

    Tolerant of an empty pick list, because the readout renders from the first
    screen onward -- before anything is loved there is simply nothing read, and
    that is a state to show rather than an error.
    """
    try:
        est = quiz.estimate(req.loved, req.disliked, rows=_games())
    except ValueError:
        return EstimateResponse(dimensions={
            d: Dimension(value=0.5, informative=0, read=False,
                         label=quiz.LABELS[d][0], gloss=quiz.LABELS[d][1])
            for d in quiz.DIMENSIONS
        })
    return EstimateResponse(dimensions=_dimensions(est))


@api.post("/quiz/fill", response_model=NextResponse)
def quiz_fill(req: FillRequest) -> NextResponse:
    """Stage 2: one card for a dimension the grid left unread, or None."""
    item = quiz.fill_item(req.served, req.loved, req.disliked, _games(), asked=req.asked)
    return NextResponse(item=None if item is None else _to_game(item), asked=req.asked)


@api.post("/quiz/sharpen", response_model=SharpenResponse)
def quiz_sharpen(req: SharpenRequest) -> SharpenResponse:
    """Stage 3: a contrastive pair on the axis that would change the answer."""
    rows = _games()
    try:
        est = quiz.estimate(req.loved, req.disliked, rows=rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if req.comparisons:
        est = quiz.apply_comparisons(
            est, [c.model_dump() for c in req.comparisons], rows)
    found = quiz.sharpen(est, used=req.used)
    if found is None:
        return SharpenResponse()
    dimension, a, b = found
    label, gloss = quiz.LABELS[dimension]
    loved = {g["game_id"] for g in est.loved}
    both = a["game_id"] in loved and b["game_id"] in loved
    return SharpenResponse(
        dimension=dimension, label=label, gloss=gloss,
        pair=[_to_game(a), _to_game(b)],
        question=("You liked both. Which more?" if both
                  else "Which would you go back to?"),
    )


@api.post("/quiz/next", response_model=NextResponse)
def next_item(req: NextRequest) -> NextResponse:
    item = quiz.next_item(req.served, req.loved, req.disliked, _games())
    return NextResponse(
        item=None if item is None
        else _to_game(item),
        asked=len(req.served),
    )


@api.post("/quiz/result", response_model=Result)
def result(req: ResultRequest) -> Result:
    rows = _games()
    try:
        est = quiz.estimate(req.loved, req.disliked, rows=rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if req.comparisons:
        est = quiz.apply_comparisons(
            est, [c.model_dump() for c in req.comparisons], rows)

    return Result(
        point=list(est.point),
        dimensions=_dimensions(est),
        champions=[
            Match(champion_id=m.champion_id, name=m.name, role=m.role,
                  distance=round(m.distance, 3), confidence=m.confidence,
                  because=quiz.explain(est, m))
            for m in quiz.champions_for(est, n=req.n)
        ],
        unknown=est.unknown,
        unread={
            d: [
                _to_game(g)
                for g in quiz.suggest_for(
                    d, exclude=est.answered, rows=rows, n=4
                )
            ]
            for d in est.unread
        },
    )


app.include_router(api)


# ---------------------------------------------------------------------------
# The built frontend, served from the same origin.
# ---------------------------------------------------------------------------
#
# One service rather than two. Same origin means no CORS to configure, no API
# base URL that differs between laptop and deployment, and nothing to get
# wrong when the host name changes. In development Vite proxies /api to this
# process and none of this is mounted, because web/dist does not exist.
#
# Mounted after every route above: a catch-all added earlier would shadow
# them. The catch-all returns index.html so a refresh on any path still loads
# the app rather than a 404.
_DIST = ROOT / "web" / "dist"

if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        # An unmatched /api path is a 404, not the app. Letting the catch-all
        # answer it returns HTML with a 200, the frontend parses it as JSON and
        # dies -- the blank page this project already fixed once, arriving back
        # through the deployment shape.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="no such endpoint")
        candidate = _DIST / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
