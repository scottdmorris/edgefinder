"""Answer plain-English stat questions from the game logs, with no guessing.

"How often has Brunson scored over 24 in his last 10?" becomes a `Query`
(who, which stat, which comparison and line, which games), and `answer`
counts the matching games. Code computes every number; there is no language
model anywhere. A question that cannot be understood completely, or whose
player is ambiguous, gets a `ParseFailure` that says what was missing, never
a best guess.

`Query` is deliberately the whole contract: a future language-model parser
only has to produce one (`Query.from_dict` validates it), and `answer` works
the same regardless of who built it.

Rules worth knowing:
- "over 24" is strictly more than 24; "24+" and "at least 24" are 24 or more.
- A whole-number line landed on exactly is a push for over/under: neither
  over nor under (as in `nba_player_lookup.hit_rate`). Pushes still count as
  games considered, so the percentage matches `hit_rate`.
- No window given means this season (the newest season in the data). There is
  no silent fall-back to last season; a player with no games gets "0 games".
- "last N" with a home/away filter means the last N home (or away) games.
- Numbers must be digits. "twenty" is refused with a message, not converted.
"""

import difflib
import math
import numbers
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ..data.nba_players import normalize_name
from .nba_player_lookup import plain_letters, search

STAT_COLUMNS = {"points": "pts", "rebounds": "reb", "assists": "ast", "threes": "fg3m"}
STAT_LABELS = {"points": "points", "rebounds": "rebounds", "assists": "assists",
               "threes": "3-pointers"}
COMPARISONS = ("over", "under", "at_least", "at_most")
WINDOWS = ("last_n", "season")
VENUES = (None, "home", "away")
REQUIRED_COLUMNS = ("player_id", "player_name", "team", "game_date", "season", "pts", "reb",
                    "ast", "fg3m", "opponent", "is_home", "wl")
_COMPARISON_PHRASES = {"over": "more than", "under": "fewer than",
                       "at_least": "at least", "at_most": "at most"}

SUPPORTED_EXAMPLES = (
    "How often has Brunson scored over 24 in his last 10?",
    "Did Jokic get 10+ rebounds this season?",
    "Brown points under 19.5 at home",
    "Luka Doncic at least 8 assists last 5 games",
    "Gary Trent Jr. 3+ threes on the road",
)
HELP_TEXT = (
    "I can answer one kind of question: how often one player went over, under, "
    "or reached a number in points, rebounds, assists or 3-pointers, using games "
    "already played. Name the player, the stat, the line (written as digits), "
    "and optionally the window (\"last 10\" or \"this season\", the default) and "
    "\"at home\" or \"on the road\". I can't do predictions, averages, "
    "opponents, playoffs, other seasons, other stats or combined stats. Examples: "
    + " / ".join(f"\"{example}\"" for example in SUPPORTED_EXAMPLES))


# ----------------------------------------------------------------------------
# The query
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class Query:
    """A fully specified question. Exactly one of `player_id` (resolved) and
    `player_text` (a name still to be resolved) is set."""
    stat: str
    comparison: str
    threshold: float
    window: str = "season"
    last_n: int | None = None
    venue: str | None = None
    player_id: int | None = None
    player_text: str | None = None

    def __post_init__(self):
        if self.stat not in STAT_COLUMNS:
            raise ValueError(f"stat must be one of {sorted(STAT_COLUMNS)}, got {self.stat!r}")
        if self.comparison not in COMPARISONS:
            raise ValueError(f"comparison must be one of {list(COMPARISONS)}, got {self.comparison!r}")
        if not _is_real_number(self.threshold) or not math.isfinite(self.threshold) \
                or self.threshold < 0:
            raise ValueError(f"threshold must be a finite number of 0 or more, got {self.threshold!r}")
        object.__setattr__(self, "threshold", float(self.threshold))
        if self.window not in WINDOWS:
            raise ValueError(f"window must be one of {list(WINDOWS)}, got {self.window!r}")
        if self.window == "last_n":
            if not _is_integer(self.last_n) or self.last_n < 1:
                raise ValueError("last_n must be a whole number of 1 or more when window is 'last_n'")
            object.__setattr__(self, "last_n", int(self.last_n))
        elif self.last_n is not None:
            raise ValueError("last_n only applies when window is 'last_n'")
        if self.venue not in VENUES:
            raise ValueError(f"venue must be None, 'home' or 'away', got {self.venue!r}")
        has_id, has_text = self.player_id is not None, self.player_text is not None
        if has_id == has_text:
            raise ValueError("give exactly one of player_id and player_text")
        if has_id:
            if not _is_integer(self.player_id):
                raise ValueError(f"player_id must be a whole number, got {self.player_id!r}")
            object.__setattr__(self, "player_id", int(self.player_id))
        else:
            if not isinstance(self.player_text, str) or not self.player_text.strip():
                raise ValueError("player_text must be non-empty text")
            object.__setattr__(self, "player_text", self.player_text.strip())

    def to_dict(self) -> dict[str, Any]:
        return {"player_id": self.player_id, "player_text": self.player_text,
                "stat": self.stat, "comparison": self.comparison,
                "threshold": self.threshold, "window": self.window,
                "last_n": self.last_n, "venue": self.venue}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Query":
        """Build a Query from plain data (for instance from a model's JSON),
        raising ValueError on anything missing, unknown or invalid."""
        if not isinstance(data, Mapping):
            raise ValueError("a query must be a mapping of field names to values")
        allowed = {f for f in cls.__dataclass_fields__}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValueError(f"unknown query fields: {unknown}")
        missing = [name for name in ("stat", "comparison", "threshold") if name not in data]
        if missing:
            raise ValueError(f"missing query fields: {missing}")
        return cls(**dict(data))


def _is_real_number(value) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _is_integer(value) -> bool:
    return isinstance(value, numbers.Integral) and not isinstance(value, bool)


# ----------------------------------------------------------------------------
# Failures and answers
# ----------------------------------------------------------------------------

@dataclass(frozen=True)
class ParseFailure:
    """The question could not be turned into a Query. `reason` is the first
    problem's code, `reasons` all of them; `message` is ready to show;
    `candidates` lists players when the name was ambiguous or nearly matched."""
    reason: str
    message: str
    candidates: tuple[str, ...] = ()
    reasons: tuple[str, ...] = field(default=())

    @property
    def supported(self) -> tuple[str, ...]:
        return SUPPORTED_EXAMPLES


@dataclass(frozen=True, eq=False)
class Answer:
    """The computed answer. `percentage` is None when no games qualified,
    never 0, because "no games" is not "0 percent"."""
    query: Query
    player_name: str
    count: int
    pushes: int
    games_considered: int
    percentage: float | None
    games: pd.DataFrame
    summary: str


def unsupported(detail: str = "") -> ParseFailure:
    """The response for a question outside what can be answered."""
    lead = f"{detail} " if detail else "That isn't a question I can answer. "
    return ParseFailure("unsupported", lead + HELP_TEXT, reasons=("unsupported",))


# ----------------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------------

_NUM = r"\d+(?:\.\d+)?"
_UNSUPPORTED_WORDS = {
    "career": "career totals", "playoffs": "playoffs", "playoff": "playoffs",
    "postseason": "playoffs", "versus": "opponent filters", "vs": "opponent filters",
    "against": "opponent filters", "average": "averages", "avg": "averages",
    "averaging": "averages", "mean": "averages", "median": "averages",
    "tonight": "predictions", "tomorrow": "predictions", "predict": "predictions",
    "prediction": "predictions", "projected": "predictions", "projection": "predictions",
    "forecast": "predictions", "odds": "odds", "expect": "predictions",
    "expected": "predictions", "minutes": "minutes as a stat", "steals": "steals",
    "steal": "steals", "blocks": "blocks", "block": "blocks", "turnovers": "turnovers",
    "fouls": "fouls", "double": "double-doubles", "doubles": "double-doubles",
    "triple": "triple-doubles", "quarter": "quarter splits", "half": "half splits",
    "combined": "combined stats", "pra": "combined stats", "since": "date ranges",
    "before": "date ranges", "after": "date ranges", "between": "date ranges",
    "month": "date ranges",
}
_UNSUPPORTED_PHRASES = (
    (r"\blast\s+(?:season|year)\b", "other seasons"),
    (r"\bback[\s-]to[\s-]back\b", "back-to-back splits"),
    (r"\bper\s+(?:game|36|48)\b", "per-game rates"),
)
_NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety", "hundred", "dozen",
}
_STRONG_STATS = {
    "points": "points", "point": "points", "pts": "points",
    "rebounds": "rebounds", "rebound": "rebounds", "rebs": "rebounds", "reb": "rebounds",
    "boards": "rebounds", "assists": "assists", "assist": "assists", "ast": "assists",
    "dimes": "assists",
}
_WEAK_POINTS = {"score", "scored", "scores", "scoring"}   # only mean points if no other stat
_STOPWORDS = {
    "how", "often", "many", "much", "times", "time", "has", "have", "had", "did", "does",
    "do", "is", "was", "were", "are", "get", "got", "gets", "getting", "hit", "hits",
    "made", "make", "makes", "record", "recorded", "grab", "grabbed", "in", "on", "of",
    "the", "a", "an", "his", "her", "their", "he", "she", "they", "him", "with", "for",
    "and", "to", "than", "game", "games", "last", "past", "previous", "recent", "this",
    "that", "what", "whats", "tell", "me", "show", "percentage", "percent", "rate",
    "chance", "number", "at", "or", "it", "i", "my", "you", "please", "player",
}

_THREES = re.compile(r"\b(?:3|three)[ -]?(?:pointers?|point|pm|s)\b")
_AWAY = re.compile(r"\b(?:away\s+from\s+home|on\s+the\s+road|road\s+games?|away(?:\s+games?)?|road)\b")
_HOME = re.compile(r"\b(?:at\s+home|home(?:\s+games?|\s+court)?)\b")
_SEASON = re.compile(r"\b(?:(?:this|the|current)\s+(?:season|year)|so\s+far|season)\b")
_LAST_N = re.compile(rf"\b(?:last|past|previous|recent)\s+({_NUM})(?:\s+(?:games?|contests?|outings?))?\b")
_LAST_ONE = re.compile(r"\b(?:last|latest|previous)\s+(?:game|outing)\b")
_PLUS = re.compile(rf"({_NUM})\s*\+")
_NUMBER = re.compile(rf"{_NUM}|\.\d+")
_COMPARISON_PATTERNS = (               # order matters: longest phrases first
    ("at_least", r"\bno\s+(?:fewer|less)\s+than\b"),
    ("at_most", r"\bno\s+more\s+than\b"),
    ("at_least", r"\bat\s+least\b"),
    ("at_most", r"\bat\s+most\b"),
    ("at_least", r"\bor\s+(?:more|better|higher|above)\b"),
    ("at_most", r"\bor\s+(?:fewer|less|lower|under|below)\b"),
    ("over", r"\b(?:over|more\s+than|above|exceed(?:ed|s)?|greater\s+than|higher\s+than)\b"),
    ("under", r"\b(?:under|less\s+than|fewer\s+than|below|lower\s+than)\b"),
)


def _clean(question: str) -> str:
    text = plain_letters(question).lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"'s\b", "", text).replace("'", "")
    return re.sub(r"(?<=[a-z])\.(?=[a-z])", "", text)           # P.J. -> pj.


def _strip(pattern: re.Pattern, text: str) -> tuple[list, str]:
    """All matches of `pattern` (as match objects) and the text without them."""
    found = list(pattern.finditer(text))
    return found, pattern.sub(" ", text)


def _unsupported_detail(text: str) -> str | None:
    kinds = []
    for word in re.findall(r"[a-z0-9]+", text):
        if word in _UNSUPPORTED_WORDS and _UNSUPPORTED_WORDS[word] not in kinds:
            kinds.append(_UNSUPPORTED_WORDS[word])
    for pattern, kind in _UNSUPPORTED_PHRASES:
        if re.search(pattern, text) and kind not in kinds:
            kinds.append(kind)
    if not kinds:
        return None
    return "I can't answer questions about " + ", ".join(kinds) + "."


def _window_and_venue(text: str) -> tuple[dict, list, str]:
    """Pull out the venue and window phrases. Returns the parsed pieces,
    issues found, and the text left over."""
    issues, parsed = [], {"venue": None, "window": None, "last_n": None}
    away, text = _strip(_AWAY, text)
    home, text = _strip(_HOME, text)
    if away and home:
        issues.append(("conflicting_venue", "you mentioned both home and away games"))
    else:
        parsed["venue"] = "away" if away else "home" if home else None
    windows = set()
    for match in _LAST_N.finditer(text):
        try:
            count = float(match.group(1))
        except ValueError:
            count = 0.0
        if count < 1 or count != int(count):
            issues.append(("bad_window", f"\"last {match.group(1)}\" isn't a whole number of games"))
        else:
            windows.add(("last_n", int(count)))
    text = _LAST_N.sub(" ", text)
    if _LAST_ONE.search(text):
        windows.add(("last_n", 1))
        text = _LAST_ONE.sub(" ", text)
    seasons, text = _strip(_SEASON, text)
    if seasons:
        windows.add(("season", None))
    if len(windows) > 1:
        issues.append(("conflicting_window", "pick one window: either the last N games or this season"))
    elif windows:
        parsed["window"], parsed["last_n"] = next(iter(windows))
    return parsed, issues, text


def _comparisons_and_numbers(text: str) -> tuple[set, set, str]:
    """Comparison kinds and candidate lines found, and the text left over."""
    comparisons, lines = set(), set()
    for match in _PLUS.finditer(text):
        comparisons.add("at_least")
        lines.add(float(match.group(1)))
    text = _PLUS.sub(" ", text)
    for kind, pattern in _COMPARISON_PATTERNS:
        compiled = re.compile(pattern)
        if compiled.search(text):
            comparisons.add(kind)
            text = compiled.sub(" ", text)
    for match in _NUMBER.finditer(text):
        lines.add(float(match.group()))
    return comparisons, lines, _NUMBER.sub(" ", text)


def _take_threes(text: str) -> tuple[set, str]:
    """Remove 3-pointer wording before numbers are read, so the 3 in "3s" or
    "3-pointers" is not mistaken for a line."""
    if _THREES.search(text):
        return {"threes"}, _THREES.sub(" ", text)
    return set(), text


def _stats_and_leftover(text: str) -> tuple[set, list[str]]:
    stats, weak, leftover = set(), False, []
    for word in re.findall(r"[a-z]+(?:-[a-z]+)*", text):
        if word in _STRONG_STATS:
            stats.add(_STRONG_STATS[word])
        elif word in _WEAK_POINTS:
            weak = True
        elif word not in _STOPWORDS:
            leftover.append(word)
    if weak and not stats:
        stats.add("points")
    return stats, leftover


def _list_words(items) -> str:
    items = sorted(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def parse(question: str, games: pd.DataFrame) -> Query | ParseFailure:
    """Turn a question into a Query, or say exactly what was missing or
    ambiguous. Never guesses: an ambiguous name asks for clarification."""
    if not isinstance(question, str) or not question.strip():
        return ParseFailure("empty", "Ask a question first. " + HELP_TEXT, reasons=("empty",))
    text = _clean(question)
    detail = _unsupported_detail(text)
    if detail:
        return unsupported(detail)

    parsed, issues, text = _window_and_venue(text)
    stats, text = _take_threes(text)
    comparisons, lines, text = _comparisons_and_numbers(text)
    stats_found, leftover = _stats_and_leftover(text)
    stats |= stats_found
    words = [w for w in re.findall(r"[a-z]+", text) if w in _NUMBER_WORDS]

    recognised = stats or comparisons or lines or parsed["window"] or parsed["venue"]
    if not recognised and not issues and not words:
        return unsupported("I couldn't find a stat question in that.")

    if words:
        issues.append(("number_words", "write numbers as digits (for example 20, not "
                                       f"\"{words[0]}\")"))
    player_id, player_issue, candidates = _resolve(games, " ".join(w for w in leftover
                                                                   if w not in _NUMBER_WORDS))
    if player_issue:
        issues.insert(0, player_issue)
    if not stats:
        issues.append(("no_stat", "which stat you mean (points, rebounds, assists or threes)"))
    elif len(stats) > 1:
        issues.append(("ambiguous_stat", f"more than one stat ({_list_words(stats)}); "
                                         "ask about one at a time"))
    if not comparisons:
        issues.append(("no_comparison", "whether you mean over, under, at least or at most"))
    elif len(comparisons) > 1:
        issues.append(("conflicting_comparison", "more than one comparison "
                                                 f"({_list_words(comparisons)}); pick one"))
    if not lines and not words:
        issues.append(("no_threshold", "the number to compare against (for example 24 or 24.5)"))
    elif len(lines) > 1:
        issues.append(("ambiguous_threshold", "more than one number to compare against ("
                       + _list_words(_format_number(v) for v in lines) + ")"))
    if issues:
        message = "I couldn't answer that: " + "; ".join(text for _, text in issues) + \
                  f". Try something like \"{SUPPORTED_EXAMPLES[0]}\""
        return ParseFailure(issues[0][0], message, tuple(candidates),
                            tuple(code for code, _ in issues))
    return Query(player_id=player_id, stat=next(iter(stats)), comparison=next(iter(comparisons)),
                 threshold=next(iter(lines)), window=parsed["window"] or "season",
                 last_n=parsed["last_n"], venue=parsed["venue"])


# ----------------------------------------------------------------------------
# Player resolution
# ----------------------------------------------------------------------------

def _label(row) -> str:
    return f"{row.player_name} ({row.team})"


def _resolve(games: pd.DataFrame, text: str) -> tuple[int | None, tuple[str, str] | None, list[str]]:
    """The one player the text names, or why not. Whole-word matches beat
    partial ones; if more than one player is still equally good, ask."""
    words = normalize_name(text).split()
    if not words:
        return None, ("no_player", "which player you mean"), []
    found = search(games, text, limit=500)
    if found.empty:
        suggestions = _near_misses(games, words)
        hint = f" Did you mean {_list_words(suggestions)}?" if suggestions else ""
        return None, ("unknown_player", f"no player matches \"{text}\".{hint}"), suggestions
    whole = found[[set(words) <= set(normalize_name(n).split()) for n in found["player_name"]]]
    best = whole if not whole.empty else found
    if len(best) > 1:                      # a typed suffix ("Jr.") can settle it
        typed = _raw_tokens(text)
        exact = best[[_raw_tokens(n) == typed for n in best["player_name"]]]
        best = exact if len(exact) == 1 else best
    if len(best) == 1:
        return int(best["player_id"].iloc[0]), None, []
    labels = [_label(row) for row in best.head(8).itertuples()]
    more = f" and {len(best) - 8} more" if len(best) > 8 else ""
    return None, ("ambiguous_player",
                  f"\"{text}\" could be {_list_words(labels)}{more}; which one do you mean?"), labels


def _raw_tokens(name: str) -> list[str]:
    """Name words with accents and punctuation gone but suffixes kept."""
    return re.findall(r"[a-z0-9]+", plain_letters(name).lower().replace("-", " "))


def _near_misses(games: pd.DataFrame, words: list[str]) -> list[str]:
    """Players whose names are close to a misspelled word. Suggestions only."""
    latest = games.drop_duplicates("player_id", keep="last")
    by_token: dict[str, list[str]] = {}
    for row in latest.itertuples():
        for token in normalize_name(row.player_name).split():
            by_token.setdefault(token, []).append(_label(row))
    scores: dict[str, int] = {}
    for word in words:
        for token in difflib.get_close_matches(word, list(by_token), n=3, cutoff=0.75):
            for label in by_token[token]:
                scores[label] = scores.get(label, 0) + 1
    return sorted(scores, key=lambda label: (-scores[label], label))[:5]


def resolve_player(games: pd.DataFrame, text: str) -> int | ParseFailure:
    """Public wrapper: a player id for a typed name, or a ParseFailure."""
    player_id, issue, candidates = _resolve(games, text)
    if issue:
        return ParseFailure(issue[0], f"I couldn't pick a player: {issue[1]}",
                            tuple(candidates), (issue[0],))
    return player_id


# ----------------------------------------------------------------------------
# Answering
# ----------------------------------------------------------------------------

def _outcomes(values: pd.Series, comparison: str, line: float) -> tuple[pd.Series, pd.Series]:
    """(hit, push) masks. Pushes exist only for over/under on a whole line."""
    if comparison == "over":
        hit = values > line
    elif comparison == "under":
        hit = values < line
    elif comparison == "at_least":
        hit = values >= line
    else:
        hit = values <= line
    push = (values == line) if comparison in ("over", "under") and float(line).is_integer() \
        else pd.Series(False, index=values.index)
    return hit, push


def _select_games(query: Query, games: pd.DataFrame, player_id: int) -> tuple[pd.DataFrame, str | None]:
    """The player's games in the question's window, oldest first, and the
    season used (for a season window)."""
    column = STAT_COLUMNS[query.stat]
    history = games[games["player_id"] == player_id]
    season = None
    if query.window == "season":
        seasons = sorted(games["season"].dropna().unique())
        season = seasons[-1] if seasons else None
        history = history[history["season"] == season]
    if query.venue == "home":
        history = history[history["is_home"].eq(True)]
    elif query.venue == "away":
        history = history[history["is_home"].eq(False)]
    history = history[history[column].notna()].sort_values("game_date", kind="stable")
    if query.window == "last_n":
        history = history.tail(query.last_n)
    return history, season


def _table(query: Query, picked: pd.DataFrame, hit: pd.Series, push: pd.Series) -> pd.DataFrame:
    label = STAT_LABELS[query.stat].capitalize()
    outcome = ["Push" if p else "Hit" if h else "Miss" for h, p in zip(hit, push)]
    table = pd.DataFrame({
        "Date": picked["game_date"].dt.strftime("%b %d, %Y"),
        "Opponent": [("vs " if home else "@ ") + str(opp)
                     for home, opp in zip(picked["is_home"], picked["opponent"])],
        "Result": picked["wl"].fillna("").to_numpy(),
        label: picked[STAT_COLUMNS[query.stat]].to_numpy(),
        "Outcome": outcome,
    }, index=picked.index)
    return table.iloc[::-1].reset_index(drop=True)                    # newest first


def _games_phrase(n: int, venue: str | None) -> str:
    return f"{n} {venue + ' ' if venue else ''}game{'' if n == 1 else 's'}"


def _summary(query: Query, name: str, count: int, pushes: int, n: int,
             pct: float | None, season: str | None) -> str:
    claim = (f"{_COMPARISON_PHRASES[query.comparison]} {_format_number(query.threshold)} "
             f"{STAT_LABELS[query.stat]}")
    venue = query.venue
    if query.window == "season":
        scope = f"the {season} season" if season else "the current season"
        if n == 0:
            return f"{name} has no {venue + ' ' if venue else ''}games in {scope} on record, " \
                   "so there is nothing to count."
        head = f"{name} had {claim} in {count} of {_games_phrase(n, venue)} in {scope}"
    else:
        asked = query.last_n
        if n == 0:
            return f"{name} has no {venue + ' ' if venue else ''}games on record, " \
                   "so there is nothing to count."
        if n < asked:
            head = f"{name} had {claim} in {count} of {_games_phrase(n, venue)}"
        elif asked == 1:
            head = f"{name} had {claim} in {count} of the last {_games_phrase(1, venue)}"
        else:
            head = f"{name} had {claim} in {count} of the last {_games_phrase(n, venue)}"
    text = f"{head} ({_format_number(round(pct, 1))}%)."
    if query.window == "last_n" and n < query.last_n:
        text += f" Only {n} were on record, fewer than the {query.last_n} asked for."
    if pushes:
        text += (f" {name} landed on exactly {_format_number(query.threshold)} in "
                 f"{_games_phrase(pushes, None)}, which counts as neither over nor under.")
    return text


def answer(query: Query, games: pd.DataFrame) -> Answer | ParseFailure:
    """Count the games that match. A ParseFailure comes back only when the
    query holds a player name that is unknown or ambiguous."""
    missing = [col for col in REQUIRED_COLUMNS if col not in games.columns]
    if missing:
        raise ValueError(f"games is missing columns: {missing}")
    player_id = query.player_id
    if player_id is None:
        resolved = resolve_player(games, query.player_text)
        if isinstance(resolved, ParseFailure):
            return resolved
        player_id = resolved
    picked, season = _select_games(query, games, player_id)
    owner = games[games["player_id"] == player_id]
    name = str(owner["player_name"].iloc[-1]) if len(owner) else f"Player {player_id}"
    values = picked[STAT_COLUMNS[query.stat]]
    hit, push = _outcomes(values, query.comparison, query.threshold)
    n, count, pushes = len(picked), int(hit.sum()), int(push.sum())
    pct = count / n * 100.0 if n else None
    return Answer(query=query, player_name=name, count=count, pushes=pushes,
                  games_considered=n, percentage=pct, games=_table(query, picked, hit, push),
                  summary=_summary(query, name, count, pushes, n, pct, season))


def ask(question: str, games: pd.DataFrame) -> Answer | ParseFailure:
    """Question in, Answer or ParseFailure out: `parse` then `answer`."""
    parsed = parse(question, games)
    return parsed if isinstance(parsed, ParseFailure) else answer(parsed, games)
