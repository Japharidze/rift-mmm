"""HTTP layer over the quiz.

Thin on purpose: every endpoint is a call into r3m, which is where the
behaviour and its reasoning live. If something here grows a rule of its own —
how to aggregate picks, when a dimension counts as read, what makes a match
close — it belongs in the package instead, or it becomes a second place the
rule exists and the two drift. That has already happened three times in this
project (the bank flag, "which labels are current", the exclusion list), so it
is worth being blunt about.
"""

import logging
import os
import subprocess
from functools import cache
from typing import Any, Literal

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


def _champion_version() -> str:
    with db.connect() as conn:
        rows = db.champion_points(conn)
    return rows[0]["prompt_version"] if rows else "unknown"


def _games() -> list[dict[str, Any]]:
    with db.connect() as conn:
        return db.game_points(conn)


def _champions() -> list[dict[str, Any]]:
    with db.connect() as conn:
        return db.champion_points(conn)


@cache
def _commit() -> str | None:
    # Railway sets this for GitHub deploys; the image has no .git to ask.
    sha = os.environ.get("RAILWAY_GIT_COMMIT_SHA")
    if sha:
        return sha
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _build(games: list[dict[str, Any]]) -> dict[str, Any]:
    """What produced a stored result (migration 019): enough to know which
    sessions a replay must re-score rather than trust."""
    return {
        "commit": _commit(),
        "serving": quiz.SERVING,
        "game_runs": sorted({r["label_run_id"] for r in games if r.get("label_run_id")}),
        "champion_runs": sorted({r["label_run_id"] for r in _champions() if r.get("label_run_id")}),
        "evidence": {"love_reasons": {"asked": list(quiz.ASK_REASON_LEVELS), "multi": True},
                     "needed": quiz.NEEDED, "dislike_weight": quiz.DISLIKE_WEIGHT,
                     "dislike_margin": quiz.DISLIKE_MARGIN, "low_corner": quiz.LOW_CORNER,
                     "unconfirmed": quiz.UNCONFIRMED},
    }


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
    # Whether a love of this game gets "what made it stick?" (quiz.asks_love_reason).
    # A flag, not the bias level: the rule stays on the server.
    ask_reason: bool = False


def _to_game(g: dict[str, Any]) -> Game:
    appid = g.get("steam_appid")
    return Game(
        id=g["game_id"],
        name=g["name"],
        mode=g["mode"],
        cover_url=STEAM_COVER.format(appid=appid) if appid else None,
        year=g.get("release_year"),
        ask_reason=quiz.asks_love_reason(g),
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


class DeepAnswer(BaseModel):
    question: str
    option: str | None = None


class DeepRequest(BaseModel):
    loved: list[str] = Field(default_factory=list)
    reasons: dict[str, str | list[str]] = Field(default_factory=dict)
    answered: list[DeepAnswer] = Field(default_factory=list)


class ResultRequest(BaseModel):
    loved: list[str]
    disliked: list[str] = Field(default_factory=list)
    n: int = 5
    # Asked before the reveal since 2026-09-30, so they arrive with the first
    # result rather than refining it.
    comparisons: list[Comparison] = Field(default_factory=list)
    # Deep-dive answers: {question, option}, option null when skipped.
    deep_dives: list[DeepAnswer] = Field(default_factory=list)
    # The developer view, requested by the page when opened with ?debug=1.
    debug: bool = False
    # Set on every re-post after the first result, so sharpening updates the
    # session it belongs to instead of recording another one.
    session_id: int | None = None
    # Slice 1 (docs/quiz-chain.md §3): every recognised game's verdict, the
    # one-tap reasons, and every card shown. Optional so older clients work.
    verdicts: dict[str, str] = Field(default_factory=dict)
    reasons: dict[str, str | list[str]] = Field(default_factory=dict)
    served: list[str] = Field(default_factory=list)
    # Panel round 2: the raw answer log, so round 2 can be replayed against
    # any later estimator (migration 019). Stored as sent.
    events: list[dict[str, Any]] = Field(default_factory=list)


class ProgressRequest(BaseModel):
    """Where a quiz has got to (migration 022): sent at the first answer and at
    every step after, so an abandoned session is still counted."""
    session_id: int | None = None
    step: str
    served: list[str] = Field(default_factory=list)
    loved: list[str] = Field(default_factory=list)
    disliked: list[str] = Field(default_factory=list)
    verdicts: dict[str, str] = Field(default_factory=dict)
    reasons: dict[str, str | list[str]] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    deep_dives: list[DeepAnswer] = Field(default_factory=list)
    comparisons: list[Comparison] = Field(default_factory=list)


class UnresolvedRequest(BaseModel):
    """A quiz that reached its end without a result (migration 020)."""
    outcome: Literal["loved_nothing", "no_gameplay_love"]
    served: list[str] = Field(default_factory=list)
    loved: list[str] = Field(default_factory=list)
    disliked: list[str] = Field(default_factory=list)
    verdicts: dict[str, str] = Field(default_factory=dict)
    reasons: dict[str, str | list[str]] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    # Set when the same player ends without a result a second time.
    session_id: int | None = None


class FillRequest(BaseModel):
    served: list[str] = Field(default_factory=list)
    loved: list[str] = Field(default_factory=list)
    disliked: list[str] = Field(default_factory=list)
    asked: int = 0
    reasons: dict[str, str | list[str]] = Field(default_factory=dict)


class EstimateRequest(BaseModel):
    loved: list[str] = Field(default_factory=list)
    disliked: list[str] = Field(default_factory=list)
    reasons: dict[str, str | list[str]] = Field(default_factory=dict)


class RoundRequest(BaseModel):
    index: int = 0
    # Recognised so far -- loved, fine or disliked -- which is what the stop
    # rule counts; "fine" is in here and nowhere else.
    played: list[str] = Field(default_factory=list)
    loved: list[str] = Field(default_factory=list)
    disliked: list[str] = Field(default_factory=list)
    reasons: dict[str, str | list[str]] = Field(default_factory=dict)
    # Every card shown so far. The fixed rounds ignore it; the card selector
    # needs it so it never repeats a card and knows what this player recognised
    # out of what they saw.
    served: list[str] = Field(default_factory=list)


class RoundResponse(BaseModel):
    index: int
    # None means the sweep is over: enough recognised and read, or no rounds left.
    cards: list[Game] | None = None


class WhyRequest(BaseModel):
    loved: list[str] = Field(default_factory=list)
    disliked: list[str] = Field(default_factory=list)
    reasons: dict[str, str | list[str]] = Field(default_factory=dict)
    asked: int = 0
    # Games already asked about and skipped: never asked twice.
    skip: list[str] = Field(default_factory=list)


class Reason(BaseModel):
    id: str
    label: str


class DeepResponse(BaseModel):
    # Ids and wording only: the axis and direction of each option stay on the
    # server, or the page would say what each answer measures.
    question: str | None = None
    game: str | None = None
    text: str | None = None
    options: list[Reason] = Field(default_factory=list)


class WhyResponse(BaseModel):
    # None when no follow-up would change the answer (quiz.why_next).
    game: Game | None = None
    kind: str | None = None
    question: str | None = None
    options: list[Reason] = Field(default_factory=list)


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
    reasons: dict[str, str | list[str]] = Field(default_factory=dict)
    deep_dives: list[DeepAnswer] = Field(default_factory=list)


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


class PanelDetails(BaseModel):
    session_id: int
    # Both optional: somebody who wants to say something but not name an
    # account, or the reverse, should be able to.
    riot_id: str | None = None
    feedback: str | None = None
    feels_right: Literal["yes", "partly", "no"] | None = None


class Result(BaseModel):
    # Present only when the session was stored; the frontend passes it back
    # when the tester offers an account or a comment.
    session_id: int | None = None

    point: list[float]
    dimensions: dict[str, Dimension]
    champions: list[Match]
    unknown: list[str]
    # Only populated for dimensions the picks could not read. Reporting the gap
    # and offering a way to close it is a frozen decision (CLAUDE.md): never
    # impute the middle.
    unread: dict[str, list[Game]]
    # ?debug=1 only (quiz.debug_view): how this result was reached. Never stored.
    debug: dict[str, Any] | None = None


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


@api.post("/quiz/round", response_model=RoundResponse)
def quiz_round(req: RoundRequest) -> RoundResponse:
    """One round of the recognition sweep, or no cards when it should stop."""
    cards = quiz.next_round(req.index, played=req.played, loved=req.loved,
                            disliked=req.disliked, reasons=req.reasons, rows=_games(),
                            shown=req.served,
                            champions=_champions() if quiz.SERVING == "selector" else None)
    return RoundResponse(index=req.index,
                         cards=None if cards is None else [_to_game(g) for g in cards])


@api.get("/quiz/reasons", response_model=WhyResponse)
def love_reasons() -> WhyResponse:
    """The love reasons, asked for every love after each round (panel round 2):
    asked of all of them, not only where this build's top five would move, so
    the answers stay usable by any later estimator."""
    labels = quiz.REASON_LABELS["love"]
    return WhyResponse(kind="love", question=quiz.WHY_QUESTION["love"],
                       options=[Reason(id=o, label=labels[o]) for o in quiz.LOVE_REASONS])


@api.post("/quiz/why", response_model=WhyResponse)
def quiz_why(req: WhyRequest) -> WhyResponse:
    """The next one-tap follow-up worth asking, or none (quiz.why_next)."""
    rows = _games()
    found = quiz.why_next(req.loved, req.disliked, req.reasons, rows, _champions(),
                          asked=req.asked, skip=req.skip)
    if found is None:
        return WhyResponse()
    game = next(r for r in rows if r["game_id"] == found["game_id"])
    labels = quiz.REASON_LABELS[found["kind"]]
    return WhyResponse(
        game=_to_game(game), kind=found["kind"], question=quiz.WHY_QUESTION[found["kind"]],
        options=[Reason(id=o, label=labels[o]) for o in found["options"]],
    )


@api.post("/quiz/estimate", response_model=EstimateResponse)
def quiz_estimate(req: EstimateRequest) -> EstimateResponse:
    """The running point, for the live readout.

    Tolerant of an empty pick list, because the readout renders from the first
    screen onward -- before anything is loved there is simply nothing read, and
    that is a state to show rather than an error.
    """
    try:
        est = quiz.estimate(req.loved, req.disliked, rows=_games(), reasons=req.reasons)
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
    item = quiz.fill_item(req.served, req.loved, req.disliked, _games(), asked=req.asked,
                          reasons=req.reasons)
    return NextResponse(item=None if item is None else _to_game(item), asked=req.asked)


@api.post("/quiz/sharpen", response_model=SharpenResponse)
def quiz_sharpen(req: SharpenRequest) -> SharpenResponse:
    """Stage 3: a contrastive pair on the axis that would change the answer."""
    rows = _games()
    try:
        est = quiz.estimate(req.loved, req.disliked, rows=rows, reasons=req.reasons)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    est = quiz.settle(est, [a.model_dump() for a in req.deep_dives],
                      [c.model_dump() for c in req.comparisons], rows)
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


@api.post("/quiz/deep", response_model=DeepResponse)
def quiz_deep(req: DeepRequest) -> DeepResponse:
    """The next deep-dive question about a game loved for the gameplay, or none."""
    q = quiz.deep_dive_next(req.loved, req.reasons, [a.model_dump() for a in req.answered])
    if q is None:
        return DeepResponse()
    return DeepResponse(question=q["id"], game=q["name"], text=q["text"],
                        options=[Reason(id=o["id"], label=o["text"]) for o in q["options"]])


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
        est = quiz.estimate(req.loved, req.disliked, rows=rows, reasons=req.reasons)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    est = quiz.settle(est, [a.model_dump() for a in req.deep_dives],
                      [c.model_dump() for c in req.comparisons], rows)

    result = Result(
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
    if req.debug:
        result.debug = quiz.debug_view(
            req.loved, req.disliked, req.reasons, [a.model_dump() for a in req.deep_dives],
            [c.model_dump() for c in req.comparisons], rows, _champions())

    # Recorded once the result exists; the session row itself starts at the first
    # answer (migration 022).
    # A failure here must not cost the tester their result: the panel is a
    # measurement we are taking, not something they asked for.
    try:
        with db.connect() as conn:
            dimensions = {d: e.model_dump() for d, e in result.dimensions.items()}
            champions = [c.model_dump() for c in result.champions]
            comparisons = [c.model_dump() for c in req.comparisons]
            updated = req.session_id is not None and db.update_quiz_session(
                conn,
                session_id=req.session_id,
                loved=req.loved,
                disliked=req.disliked,
                comparisons=comparisons,
                point=list(est.point),
                dimensions=dimensions,
                champions=champions,
                events=req.events or None,
                served=req.served or None,
                verdicts=req.verdicts or None,
                reasons=req.reasons or None,
                build=_build(rows),
                deep_dives=[a.model_dump() for a in req.deep_dives] or None,
            )
            result.session_id = req.session_id if updated else db.insert_quiz_session(
                conn,
                served=req.served or req.loved + req.disliked,
                loved=req.loved,
                disliked=req.disliked,
                comparisons=comparisons,
                point=list(est.point),
                dimensions=dimensions,
                champions=champions,
                champion_prompt_version=_champion_version(),
                game_prompt_version=rows[0]["prompt_version"] if rows else "unknown",
                verdicts=req.verdicts or None,
                reasons=req.reasons or None,
                events=req.events or None,
                build=_build(rows),
                deep_dives=[a.model_dump() for a in req.deep_dives] or None,
            )
    except Exception:  # noqa: BLE001 - see comment above
        logging.exception("could not record panel session")

    return result


@api.post("/visit")
def visit() -> dict[str, bool]:
    """The page was opened (migration 023): the top of the funnel. Nothing
    about the visitor is stored, and a failure costs them nothing."""
    try:
        with db.connect() as conn:
            db.record_visit(conn, quiz.SERVING)
        return {"stored": True}
    except Exception:  # noqa: BLE001 - see /quiz/result
        logging.exception("could not record visit")
        return {"stored": False}


@api.post("/quiz/progress")
def progress(req: ProgressRequest) -> dict[str, int | None]:
    """Record the step a session has reached. Like /quiz/result, a failure to
    store costs the player nothing."""
    try:
        rows = _games()
        with db.connect() as conn:
            return {"session_id": db.record_progress(
                conn, session_id=req.session_id, step=req.step, served=req.served,
                loved=req.loved, disliked=req.disliked, verdicts=req.verdicts,
                reasons=req.reasons, events=req.events,
                deep_dives=[a.model_dump() for a in req.deep_dives],
                comparisons=[c.model_dump() for c in req.comparisons], build=_build(rows),
                champion_prompt_version=_champion_version(),
                game_prompt_version=rows[0]["prompt_version"] if rows else "unknown")}
    except Exception:  # noqa: BLE001 - see /quiz/result
        logging.exception("could not record progress")
        return {"session_id": req.session_id}


@api.post("/quiz/unresolved")
def unresolved(req: UnresolvedRequest) -> dict[str, int | None]:
    """Record a session that ended with nothing to match on. Like /quiz/result,
    a failure to store costs the player nothing."""
    try:
        rows = _games()
        with db.connect() as conn:
            if req.session_id is not None and db.update_unresolved_session(
                    conn, session_id=req.session_id, outcome=req.outcome, served=req.served,
                    loved=req.loved, disliked=req.disliked, verdicts=req.verdicts,
                    reasons=req.reasons, events=req.events):
                return {"session_id": req.session_id}
            return {"session_id": db.insert_unresolved_session(
                conn, outcome=req.outcome, served=req.served, loved=req.loved,
                disliked=req.disliked, verdicts=req.verdicts, reasons=req.reasons,
                events=req.events, build=_build(rows),
                champion_prompt_version=_champion_version(),
                game_prompt_version=rows[0]["prompt_version"] if rows else "unknown")}
    except Exception:  # noqa: BLE001 - see /quiz/result
        logging.exception("could not record unresolved session")
        return {"session_id": None}


@api.post("/panel/details")
def panel_details(req: PanelDetails) -> dict[str, bool]:
    """Attach a Riot id and/or a comment to a session already finished."""
    with db.connect() as conn:
        ok = db.attach_panel_details(
            conn,
            session_id=req.session_id,
            riot_id=req.riot_id,
            feedback=req.feedback,
            feels_right=req.feels_right,
        )
    return {"stored": ok}


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
