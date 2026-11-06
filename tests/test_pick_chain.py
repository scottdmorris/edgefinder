import datetime as dt
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

from edgefinder.tracking import nba_paper, pick_chain

EVENT = {"event_id": "e1", "commence_time": "2026-11-05T00:00:00Z",
         "home": "Detroit Pistons", "away": "Philadelphia 76ers"}
LINES = [{"player": "Cade Cunningham", "line": 24.5, "over_odds": -110, "under_odds": -110},
         {"player": "Duncan Robinson", "line": 13.5, "over_odds": -130, "under_odds": -102}]
NOW = dt.datetime(2026, 11, 4, 20, 0, tzinfo=dt.timezone.utc)


def rows(version="ewma-v1", recorded="2026-11-04T17:00:00+00:00"):
    predictions = {"Cade Cunningham": {"player_id": 1, "mean": 32.0},
                   "Duncan Robinson": {"player_id": 2, "mean": 8.0}}
    return nba_paper.build_ledger_rows(EVENT, LINES, predictions, recorded, "2026-11-04",
                                       model_version=version, dispersion=7.8)


def four():
    """Four ledger rows: two lines priced by two models."""
    return rows() + rows("minutes-v1")


def frame(batch):
    return pd.DataFrame(batch, columns=nba_paper.COLUMNS)


@pytest.fixture
def chain(tmp_path):
    return tmp_path / "log.chain.jsonl"


def lines_of(path):
    return path.read_text(encoding="utf-8").splitlines()


def rewrite(path, edit):
    entries = [json.loads(line) for line in lines_of(path)]
    edit(entries)
    path.write_text("\n".join(json.dumps(e, sort_keys=True, separators=(",", ":"))
                              for e in entries) + "\n", encoding="utf-8")


# ---- the fingerprint -------------------------------------------------------------------------

def test_a_fingerprint_is_the_sha256_of_the_previous_one_a_newline_and_the_canonical_body():
    body = {"b": [True, None], "a": 1}                     # key order must not matter
    assert pick_chain.canonical(body) == '{"a":1,"b":[true,null]}'
    assert pick_chain.fingerprint("0" * 64, body) == (
        "0a05d27448b72bcc061f72b3778ddba4bdc6ac51fb45a1c3b51f8d211a579bcd")


def test_the_same_row_hashes_the_same_whether_numbers_are_ints_floats_or_numpy():
    import numpy as np
    a = pick_chain._data({"line": 24.5, "over_odds": -110, "player": "X"}, ("line", "over_odds"))
    b = pick_chain._data({"line": np.float64(24.5), "over_odds": np.int64(-110), "player": "X"},
                         ("line", "over_odds"))
    assert a == b == {"line": 24.5, "over_odds": -110.0}
    assert pick_chain._clean(float("nan")) is None and pick_chain._clean("") is None
    assert pick_chain._clean(None) is None and pick_chain._clean("over") == "over"


def test_nan_can_never_reach_the_file_because_json_would_not_round_trip_it():
    with pytest.raises(ValueError):
        pick_chain.canonical({"a": float("nan")})


# ---- writing and verifying -------------------------------------------------------------------

def test_entries_are_numbered_and_each_follows_the_one_before_starting_from_genesis(chain):
    assert pick_chain.record_picks(chain, four(), NOW) == 4
    entries = pick_chain.load(chain)
    assert [e["seq"] for e in entries] == [0, 1, 2, 3]
    assert entries[0]["prev"] == pick_chain.GENESIS
    assert all(entries[i]["prev"] == entries[i - 1]["hash"] for i in range(1, 4))
    result = pick_chain.verify(chain)
    assert result.intact and result.entries == 4 and result.head == entries[-1]["hash"]
    assert result.imported == 0 and result.first_at == NOW.isoformat()


def test_a_second_batch_carries_on_from_the_first(chain):
    pick_chain.record_picks(chain, rows(), NOW)
    pick_chain.record_picks(chain, rows("minutes-v1"), NOW)
    result = pick_chain.verify(chain)
    assert result.intact and result.entries == 4 and [e["seq"] for e in pick_chain.load(chain)] == [
        0, 1, 2, 3]


def test_an_empty_or_missing_chain_verifies_as_empty_and_intact(chain):
    result = pick_chain.verify(chain)
    assert result.intact and result.entries == 0 and result.head == pick_chain.GENESIS
    assert pick_chain.record_picks(chain, [], NOW) == 0 and not chain.exists()


def test_changing_any_field_in_a_past_entry_is_caught(chain):
    pick_chain.record_picks(chain, rows(), NOW)

    def edit(entries):
        entries[1]["data"]["pick_odds"] = -500.0

    rewrite(chain, edit)
    result = pick_chain.verify(chain)
    assert not result.intact
    assert any("entry 1" in p and "fingerprint" in p for p in result.problems)


def test_deleting_an_entry_from_the_middle_is_caught(chain):
    pick_chain.record_picks(chain, four(), NOW)
    rewrite(chain, lambda entries: entries.pop(1))
    result = pick_chain.verify(chain)
    assert not result.intact and any("out of order" in p or "does not follow" in p
                                     for p in result.problems)


def test_swapping_two_entries_is_caught(chain):
    pick_chain.record_picks(chain, four(), NOW)
    rewrite(chain, lambda entries: entries.__setitem__(slice(1, 3), [entries[2], entries[1]]))
    assert not pick_chain.verify(chain).intact


def test_rewriting_an_entry_and_fixing_its_own_fingerprint_still_breaks_the_next_one(chain):
    pick_chain.record_picks(chain, four(), NOW)

    def edit(entries):
        entries[1]["data"]["pick_odds"] = -500.0
        body = {k: v for k, v in entries[1].items() if k not in ("hash", "prev")}
        entries[1]["hash"] = pick_chain.fingerprint(entries[1]["prev"], body)

    rewrite(chain, edit)
    result = pick_chain.verify(chain)
    assert not result.intact and any("entry 2" in p for p in result.problems)


def test_cutting_the_end_off_looks_intact_but_not_against_a_published_fingerprint(chain):
    pick_chain.record_picks(chain, four(), NOW)
    published = pick_chain.verify(chain)
    rewrite(chain, lambda entries: entries.pop())                     # drop the last entry
    assert pick_chain.verify(chain).intact                            # a chain alone cannot tell
    assert pick_chain.holds(chain, 3, pick_chain.load(chain)[-1]["hash"])
    assert not pick_chain.holds(chain, published.entries, published.head)   # but the digest can


def test_a_published_state_is_found_in_a_log_that_has_grown_since(chain):
    pick_chain.record_picks(chain, rows(), NOW)
    published = pick_chain.verify(chain)
    pick_chain.record_picks(chain, rows("minutes-v1"), NOW)
    assert pick_chain.holds(chain, published.entries, published.head)
    assert not pick_chain.holds(chain, published.entries, "f" * 64)
    assert not pick_chain.holds(chain, 0, pick_chain.GENESIS) and not pick_chain.holds(
        chain, 99, published.head)


# ---- comparing the ledger with the chain --------------------------------------------------------

def logged_ledger(chain):
    batch = rows()
    pick_chain.record_picks(chain, batch, NOW)
    return frame(batch)


def test_an_untouched_ledger_matches_its_chain(chain):
    ledger = logged_ledger(chain)
    audit = pick_chain.audit(ledger, chain)
    assert audit.clean and audit.rows == 2 and audit.matched == 2


def test_an_edited_pick_is_named_with_the_field_that_changed(chain):
    ledger = logged_ledger(chain)
    ledger.loc[0, "pick_side"] = "under"
    audit = pick_chain.audit(ledger, chain)
    assert not audit.clean and audit.matched == 1
    assert any("edited after it was logged" in p and "pick_side" in p for p in audit.problems)


def test_a_changed_timestamp_is_caught_too(chain):
    ledger = logged_ledger(chain)
    ledger.loc[1, "recorded_at"] = "2026-11-04T01:00:00+00:00"
    assert any("recorded_at" in p for p in pick_chain.audit(ledger, chain).problems)


def test_a_deleted_row_is_caught(chain):
    ledger = logged_ledger(chain).iloc[:1]
    audit = pick_chain.audit(ledger, chain)
    assert any(p.startswith("deleted from the ledger") for p in audit.problems)


def test_a_row_added_by_hand_that_was_never_logged_is_caught(chain):
    ledger = logged_ledger(chain)
    sneaky = {**rows("minutes-v1")[0]}
    ledger = pd.concat([ledger, frame([sneaky])], ignore_index=True)
    assert any(p.startswith("not in the chain") for p in pick_chain.audit(ledger, chain).problems)


def settled_copy(ledger):
    done = ledger.copy()
    done["status"] = done["status"].astype(object)
    done.loc[0, ["status", "actual", "went_over", "result", "pnl_units"]] = [
        "settled", 30.0, True, "win", 0.909091]
    return done


def test_a_settled_row_needs_its_result_logged_and_a_matching_one(chain):
    before = logged_ledger(chain)
    after = settled_copy(before)
    assert any("result was never logged" in p for p in pick_chain.audit(after, chain).problems)
    assert pick_chain.record_settlements(chain, before, after, NOW) == 1
    assert pick_chain.audit(after, chain).clean


def test_a_result_changed_after_it_was_logged_is_caught(chain):
    before = logged_ledger(chain)
    after = settled_copy(before)
    pick_chain.record_settlements(chain, before, after, NOW)
    after.loc[0, ["result", "pnl_units"]] = ["loss", -1.0]            # a loss quietly made a win... or back
    problems = pick_chain.audit(after, chain).problems
    assert any("result differs from the one logged" in p and "pnl_units" in p for p in problems)


def test_a_logged_result_with_the_ledger_saying_pending_is_caught(chain):
    before = logged_ledger(chain)
    after = settled_copy(before)
    pick_chain.record_settlements(chain, before, after, NOW)
    assert any("has a logged result" in p for p in pick_chain.audit(before, chain).problems)


def test_only_rows_that_went_from_pending_to_settled_or_void_are_logged_as_results(chain):
    before = logged_ledger(chain)
    after = settled_copy(before)
    after.loc[1, "status"] = "void"
    logged = pick_chain.settlements(before, after)
    assert [r["player"] for r in logged] == ["Cade Cunningham", "Duncan Robinson"]
    assert pick_chain.settlements(after, after) == []                  # already done: nothing new


# ---- starting a chain from a ledger that already has rows --------------------------------------------

def test_an_existing_ledger_is_imported_once_and_marked_as_imported(chain):
    base = frame(rows())
    base = settled_copy(base)
    assert pick_chain.ensure_started(chain, base, NOW) is True
    entries = pick_chain.load(chain)
    assert [e["kind"] for e in entries] == ["pick", "pick", "result"]   # one settled row
    assert all(e["imported"] for e in entries)
    assert pick_chain.verify(chain).imported == 3
    assert pick_chain.audit(base, chain).clean
    assert pick_chain.ensure_started(chain, base, NOW) is False          # never twice


def test_an_empty_ledger_starts_no_chain(chain):
    assert pick_chain.ensure_started(chain, frame([]), NOW) is False and not chain.exists()


# ---- wired into the real ledger ---------------------------------------------------------------------

def test_new_rows_are_logged_as_they_are_written_after_the_old_ones_are_imported(tmp_path):
    ledger_path = tmp_path / "ledger.csv"
    assert nba_paper.append_rows(four(), ledger_path) == 4              # first ever write
    chain = pick_chain.chain_path_for(ledger_path)
    assert pick_chain.verify(chain).imported == 0 and pick_chain.verify(chain).entries == 4

    ledger_path2 = tmp_path / "older.csv"
    nba_paper.save_ledger(frame(rows()), ledger_path2)                  # a ledger from before
    assert nba_paper.append_rows(rows("minutes-v1"), ledger_path2) == 2
    older = pick_chain.verify(pick_chain.chain_path_for(ledger_path2))
    assert older.entries == 4 and older.imported == 2                    # 2 imported, 2 live
    assert pick_chain.audit(nba_paper.load_ledger(ledger_path2),
                            pick_chain.chain_path_for(ledger_path2)).clean


def test_appending_the_same_rows_again_adds_nothing_to_the_ledger_or_the_chain(tmp_path):
    path = tmp_path / "ledger.csv"
    nba_paper.append_rows(four(), path)
    assert nba_paper.append_rows(four(), path) == 0
    assert pick_chain.verify(pick_chain.chain_path_for(path)).entries == 4


def test_a_chain_failure_never_loses_a_pick_and_the_audit_then_shows_it_was_not_logged(
        tmp_path, monkeypatch):
    path = tmp_path / "ledger.csv"

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(pick_chain, "record_picks", broken)
    assert nba_paper.append_rows(four(), path) == 4                      # the pick is still saved
    monkeypatch.undo()
    audit = pick_chain.audit(nba_paper.load_ledger(path), pick_chain.chain_path_for(path))
    assert len(audit.problems) == 4 and all("never logged" in p for p in audit.problems)


def test_settling_through_the_ledger_logs_the_results_and_the_audit_stays_clean(tmp_path):
    path = tmp_path / "ledger.csv"
    nba_paper.append_rows(rows(), path)
    before = nba_paper.load_ledger(path)
    games = pd.DataFrame({"player_id": [1, 2], "game_date": pd.to_datetime(["2026-11-04"] * 2),
                          "pts": [30.0, 10.0]})
    empty = pd.DataFrame(columns=["fetched_at", "phase", "event_id", "player", "line",
                                  "over_odds", "under_odds"])
    after = nba_paper.settle(before, games, empty, pd.Timestamp("2026-11-06").date())
    assert nba_paper.log_settlements(before, after, path) == 2
    nba_paper.save_ledger(after, path)
    chain = pick_chain.chain_path_for(path)
    assert pick_chain.verify(chain).intact
    assert pick_chain.audit(nba_paper.load_ledger(path), chain).clean
    # a closing price arriving later is not part of the log, so it never trips the audit
    after.loc[0, "clv_pct"] = 3.0
    assert pick_chain.audit(after, chain).clean


def test_editing_the_saved_ledger_file_by_hand_is_caught_by_the_audit(tmp_path):
    path = tmp_path / "ledger.csv"
    nba_paper.append_rows(rows(), path)
    tampered = path.read_text(encoding="utf-8").replace("-110", "-210", 1)
    path.write_text(tampered, encoding="utf-8")
    audit = pick_chain.audit(nba_paper.load_ledger(path), pick_chain.chain_path_for(path))
    assert not audit.clean and any("over_odds" in p or "under_odds" in p for p in audit.problems)


# ---- the published digest ----------------------------------------------------------------------------------

@pytest.fixture
def verify_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "verify_record.py"
    spec = importlib.util.spec_from_file_location("verify_record_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_digest_line_is_the_date_the_entry_count_and_the_head(chain):
    pick_chain.record_picks(chain, four(), NOW)
    result = pick_chain.verify(chain)
    assert pick_chain.digest_line(result, dt.date(2026, 11, 5)) == (
        f"| 2026-11-05 | 4 | `{result.head}` |")


def test_writing_the_digest_adds_a_line_once_per_state(verify_script, chain, tmp_path):
    pick_chain.record_picks(chain, rows(), NOW)
    digests = tmp_path / "DIGESTS.md"
    digests.write_text("| Date | Entries | Fingerprint |\n|---|---|---|\n", encoding="utf-8")
    result = pick_chain.verify(chain)
    assert verify_script.write_digest(result, dt.date(2026, 11, 5), digests) is True
    assert verify_script.write_digest(result, dt.date(2026, 11, 6), digests) is False   # same state
    pick_chain.record_picks(chain, rows("minutes-v1"), NOW)
    assert verify_script.write_digest(pick_chain.verify(chain), dt.date(2026, 11, 6), digests)
    assert digests.read_text(encoding="utf-8").count("\n| 2026-11-") == 2


def test_the_checker_reports_a_sound_record_and_a_tampered_one(verify_script, tmp_path):
    path = tmp_path / "ledger.csv"
    nba_paper.append_rows(rows(), path)
    verification, audit = verify_script.check(path)
    assert verification.intact and audit.clean
    path.write_text(path.read_text(encoding="utf-8").replace("-110", "-210", 1), encoding="utf-8")
    verification, audit = verify_script.check(path)
    assert verification.intact and not audit.clean


# ---- reading the published fingerprints back --------------------------------------------------------------

def test_published_fingerprints_are_read_from_the_digest_file_and_junk_lines_are_skipped(tmp_path):
    head = "a" * 64
    digests = tmp_path / "DIGESTS.md"
    digests.write_text(
        "# Title\n\n| Date | Entries | Fingerprint |\n|---|---|---|\n"
        f"| 2026-11-05 | 813 | `{head}` |\n| 2026-11-06 | oops | `{head}` |\n"
        f"| 2026-11-07 | 900 | `short` |\n", encoding="utf-8")
    assert pick_chain.published(digests) == [("2026-11-05", 813, head)]
    assert pick_chain.published(tmp_path / "missing.md") == []


def test_each_published_state_is_checked_against_the_log(chain, tmp_path):
    pick_chain.record_picks(chain, four(), NOW)
    early = pick_chain.verify(chain)
    pick_chain.record_picks(chain, rows("context-v1"), NOW)
    digests = tmp_path / "DIGESTS.md"
    digests.write_text(
        pick_chain.digest_line(early, dt.date(2026, 11, 5)) + "\n"
        + f"| 2026-11-06 | 6 | `{'b' * 64}` |\n", encoding="utf-8")
    assert pick_chain.check_published(chain, digests) == [
        ("2026-11-05", 4, True), ("2026-11-06", 6, False)]       # the second one never existed
