"""The web app's API, and the built front end.

Run with:  .venv\\Scripts\\uvicorn edgefinder.api.app:app --app-dir src --port 8000

Every route reads what the scheduled jobs recorded; nothing here spends Odds API requests or
writes to the ledger. When web/dist exists (after `npm run build` in web/), the same server also
serves the app itself at "/", so one address works on a PC or a phone.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from ..data import nba_live
from . import live, picks, players, record, service, slip_review

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
MAX_LEGS = 12
MAX_STAKE = 100_000

app = FastAPI(title="Ball Knowledge", docs_url="/api/docs", openapi_url="/api/openapi.json")


class SlipRequest(BaseModel):
    date: str | None = None
    book: str | None = None
    model: str | None = None
    legs: list[int] = Field(default_factory=list, max_length=MAX_LEGS)
    stake: float = Field(default=10.0, ge=0, le=MAX_STAKE)


def _guard(call):
    try:
        return call()
    except service.NotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:          # e.g. the same player twice on one stat
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/health")
def health() -> dict:
    return service.health()


@app.get("/api/days")
def days() -> list[dict]:
    return service.days()


@app.get("/api/board")
def board(date: str | None = None, book: str | None = None, model: str | None = None) -> dict:
    return _guard(lambda: service.board(date, book, model))


@app.get("/api/ideas")
def ideas(style: str, date: str | None = None, book: str | None = None,
          model: str | None = None, game: str | None = None) -> list[dict]:
    return _guard(lambda: service.ideas(date, book, model, style, game))


@app.post("/api/slip")
def slip(request: SlipRequest) -> dict:
    return _guard(lambda: service.price_slip(request.date, request.book, request.model,
                                             request.legs, request.stake))


def _review(call):
    try:
        return _guard(call)
    except slip_review.ReviewError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from None


@app.post("/api/slip/read")
async def read_slip_images(request: Request) -> dict:
    async with request.form(max_files=5, max_fields=0) as form:
        files = [value for _, value in form.multi_items() if isinstance(value, UploadFile)]
        if not 1 <= len(files) <= 5:
            raise HTTPException(422, "Choose between one and five images.")
        if sum(file.size or 0 for file in files) > 20 * 1024 * 1024:
            raise HTTPException(413, "Images must total no more than 20 MB.")
        outputs = []
        for file in files:
            if (file.size or 0) > slip_review.MAX_FILE_BYTES:
                raise HTTPException(413, "Each image must be no larger than 8 MB.")
            data = await file.read(slip_review.MAX_FILE_BYTES + 1)
            outputs.append(await run_in_threadpool(lambda: _review(lambda: slip_review.read_image(data))))
        return {"images": outputs}


@app.post("/api/slip/match")
def match_slip(request: slip_review.MatchRequest) -> dict:
    return _review(lambda: slip_review.match_text(request.text, slip_review._table(request)))


@app.post("/api/slip/review")
def review_slip(request: slip_review.ReviewRequest) -> dict:
    return _review(lambda: slip_review.review(request))


class TrackRequest(BaseModel):
    date: str | None = None
    book: str | None = None
    model: str | None = None
    legs: list[int] = Field(default_factory=list, max_length=MAX_LEGS)


def _feed(call):
    """A live-feed route: NBA's feed being down is a 503 the page retries, not a crash."""
    try:
        return _guard(call)
    except nba_live.LiveDataError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@app.get("/api/live")
def live_games() -> list[dict]:
    return _feed(live.board)


@app.get("/api/live/{game_id}")
def live_game(game_id: str) -> dict:
    return _feed(lambda: live.game_detail(game_id))


@app.post("/api/live/track")
def live_track(request: TrackRequest) -> dict:
    return _feed(lambda: live.track(request.date, request.book, request.model, request.legs))


@app.get("/api/record")
def our_record() -> dict:
    return record.record()


@app.get("/api/picks")
def model_picks(date: str | None = None) -> dict:
    return _guard(lambda: picks.picks(date))


@app.get("/api/players")
def player_list() -> list[dict]:
    return players.players()


@app.get("/api/players/{player_id}")
def player_profile(player_id: int) -> dict:
    return _guard(lambda: players.profile(player_id))


def web_file(root: Path, path: str) -> Path | None:
    """The built file at `path`, or None when there is none or it would sit outside `root`."""
    if not path:
        return None
    base = root.resolve()
    target = (base / path).resolve()
    return target if target.is_file() and base in target.parents else None


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        """The app itself; any path that is not an API route or a file opens the app."""
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="no such API route")
        target = web_file(WEB_DIST, path)
        if target:
            return FileResponse(target)
        # the page must be re-checked each visit so a new build shows up; its scripts have
        # hashed names, so those can be cached for good
        return FileResponse(WEB_DIST / "index.html", headers={"Cache-Control": "no-cache"})
