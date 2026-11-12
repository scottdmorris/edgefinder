"""Local image OCR, conservative quote matching, and Python slip review."""

import io
import re
import threading
import warnings

import numpy as np
import pandas as pd
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from ..betting import correlated
from ..data.nba_players import normalize_name
from ..tracking import nba_parlay
from . import service

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 16_000_000
_ocr_lock = threading.Lock()
_engine = None


class ReviewError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


class MatchRequest(BaseModel):
    date: str = Field(max_length=10)
    book: str = Field(max_length=80)
    model: str = Field(max_length=80)
    text: str = Field(min_length=1, max_length=25000)


class ReviewRequest(BaseModel):
    date: str = Field(max_length=10)
    book: str = Field(max_length=80)
    model: str = Field(max_length=80)
    legs: list[int] = Field(min_length=1, max_length=12)
    confirmed: bool = False


def read_image(data: bytes) -> dict:
    global _engine
    if len(data) > MAX_FILE_BYTES:
        raise ReviewError("Each image must be no larger than 8 MB.", 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in {"PNG", "JPEG", "WEBP"}:
                    raise ReviewError("Use PNG, JPEG or WebP images.")
                if source.width * source.height > MAX_PIXELS or getattr(source, "n_frames", 1) != 1:
                    raise ReviewError("Use a single-frame image of at most 16 megapixels.")
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((2200, 3000))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ReviewError("This file could not be read as a safe image.") from None
    if not _ocr_lock.acquire(blocking=False):
        raise ReviewError("Another image is being read. Try again shortly.", 429)
    try:
        if _engine is None:
            from rapidocr import RapidOCR
            _engine = RapidOCR()
        output = _engine(np.asarray(image))
        texts = output.txts or ()
        scores = output.scores or ()
        return {"text": "\n".join(texts)[:25000],
                "low_confidence": any(float(score) < .85 for score in scores),
                "lines": len(texts)}
    except Exception:
        raise ReviewError("Local OCR could not read this image. Try a clearer crop or paste its text.", 503) from None
    finally:
        _ocr_lock.release()


def _table(request):
    table, market = service.candidates(request.date, request.book, request.model)
    if any(market[key] != getattr(request, key) for key in ("date", "book", "model")):
        raise ReviewError("The selected market is unavailable. Refresh the board.", 409)
    return table


STAT_PATTERNS = {"points": r"\b(?:points?|pts)\b", "rebounds": r"\b(?:rebounds?|reb)\b",
                 "assists": r"\b(?:assists?|ast)\b", "threes": r"\b(?:threes?|3[- ]?pointers?|3pm|3pt|three pointers)\b"}


def match_text(text: str, table: pd.DataFrame) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    names = {normalize_name(name): name for name in table["Player"].unique()}
    anchors = []
    for position, line in enumerate(lines):
        plain = " " + normalize_name(line) + " "
        matches = [name for name in names if f" {name} " in plain]
        if len(matches) == 1:
            anchors.append((position, names[matches[0]]))
    matches, seen = [], set()
    for n, (start, player) in enumerate(anchors):
        end = min(start + 6, anchors[n + 1][0] if n + 1 < len(anchors) else len(lines))
        block = " ".join(lines[start:end])
        # Kalshi prints the whole bet on the player's line ("Name: 8+ rebounds"). Read that line
        # alone, so the lines after it (other players, not on the board) cannot confuse the stat.
        own = lines[start].lower()
        if re.search(r"\d", own) and any(re.search(pattern, own) for pattern in STAT_PATTERNS.values()):
            block = lines[start]
        lower = block.lower()
        # Combined stats need their own model; never interpret PRA as points.
        combined = bool(re.search(r"\bpra\b|points\s*[+&/]\s*rebounds", lower))
        stats = [stat for stat, pattern in STAT_PATTERNS.items() if re.search(pattern, lower)]
        choices = []
        if not combined and len(stats) == 1:
            props = re.findall(r"\b(over|under|o|u)\s*(\d+(?:\.\d+)?)\b", lower)
            plus = re.findall(r"\b(\d+)\s*\+", lower)
            for index, row in table[(table["Player"] == player) & (table["stat_key"] == stats[0])].iterrows():
                exact = any(bool(row["is_over"]) == (side in {"over", "o"}) and float(row["line"]) == float(line)
                            for side, line in props)
                exact = exact or (bool(row["is_over"]) and any(float(row["line"]) == float(line) - .5 for line in plus))
                if exact:
                    choices.append(int(index))
        key = (player, block)
        if key not in seen:
            matches.append({"player": player, "text": block, "candidate_ids": choices,
                            "status": "Confirm match" if len(choices) == 1 else "Needs manual selection"})
            seen.add(key)
    return {"matches": matches, "note": "Verify every player, stat, side and line. Unknown players, combined stats and unreadable text may be unmatched. Odds below are recorded board prices, not extracted slip odds."}


def review(request: ReviewRequest) -> dict:
    if not request.confirmed:
        raise ReviewError("Confirm the extracted selections before reviewing.")
    if len(set(request.legs)) != len(request.legs):
        raise ReviewError("Remove duplicate selections before reviewing.")
    table = _table(request)
    if any(i not in table.index for i in request.legs):
        raise ReviewError("A quote changed or is unavailable. Match your slip again.", 409)
    selected = table.loc[request.legs]
    teams = service._teams()
    summary = correlated.summarise(nba_parlay.to_legs(selected, teams))
    reviews = []
    for i, row in selected.iterrows():
        ev = float(row["Leg EV %"])
        remaining = selected.drop(i)
        without = correlated.joint_probability(nba_parlay.to_legs(remaining, teams)) if len(remaining) else None
        reviews.append({"id": int(i), "player": row["Player"], "bet": row["Leg"].split(" · ", 1)[-1],
                        "projection": service._num(row.get("projection"), 1),
                        "chance_pct": service._num(row["prob"] * 100, 1), "ev_pct": service._num(ev, 1),
                        "assessment": "Consider removing" if ev < 0 else "Positive estimated value" if ev >= 2 else "Little estimated edge",
                        "reason": "Estimated return is negative at the recorded price." if ev < 0 else
                                  "Positive estimate depends on model accuracy and the available price." if ev >= 2 else
                                  "The estimated edge is small before fees.",
                        "without_chance_pct": service._num(without * 100, 1) if without is not None else None})
    reviews.sort(key=lambda item: item["ev_pct"])
    good = nba_parlay._worthwhile_legs(table)
    good = good[~good["player_id"].isin(selected["player_id"]) & ~good["event_id"].isin(selected["event_id"])]
    additions = []
    for i, row in good.sort_values("Leg EV %", ascending=False).drop_duplicates("player_id").head(3).iterrows():
        extended = pd.concat([selected, table.loc[[i]]])
        additions.append({"id": int(i), "player": row["Player"], "bet": row["Leg"].split(" · ", 1)[-1],
                          "ev_pct": service._num(row["Leg EV %"], 1),
                          "with_chance_pct": service._num(correlated.joint_probability(nba_parlay.to_legs(extended, teams)) * 100, 1)})
    return {"legs": reviews, "chance_pct": service._num(summary["joint_probability"] * 100, 1),
            "ev_pct": service._num(summary["ev_per_unit"] * 100, 1), "additions": additions if len(selected) < 12 else [],
            "notes": ["Review uses recorded board odds, not screenshot odds; fees are excluded.",
                      "Adding a leg reduces the chance of every leg winning, even with positive estimated value.",
                      "Same-game legs are correlated." if selected["event_id"].nunique() < len(selected) else "Selected legs are from separate games.",
                      "This is a model-based review, not an injury or current-availability check."]}
