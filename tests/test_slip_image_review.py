import io
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from edgefinder.api import app, service, slip_review as review


def table():
    return pd.DataFrame([{
        "Player": name, "Leg": f"{name} · Over {line} points", "player_id": i,
        "stat_key": "points", "line": line, "is_over": True, "event_id": f"game{i}",
        "prob": p, "Odds": -110, "Leg EV %": ev, "Model %": 60, "Market %": 55,
        "projection": line + 2, "Game": f"A @ B{i}",
    } for i, name, line, p, ev in [(1, "Jalen Brunson", 26.5, .48, -8.36),
                                  (2, "Nikola Jokic", 24.5, .60, 14.55),
                                  (3, "Jaylen Brown", 20.5, .60, 14.55)]], index=[11, 22, 33])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(service, "candidates", lambda *args: (table(), {"date": "2026-11-11", "book": "fanduel", "model": "minutes-v1"}))
    monkeypatch.setattr(service, "_teams", lambda: {1: "NYK", 2: "DEN", 3: "BOS"})
    return TestClient(app.app)


MARKET = {"date": "2026-11-11", "book": "fanduel", "model": "minutes-v1"}


def test_matches_exact_side_stat_and_line_and_retains_unsupported_text(client):
    result = client.post('/api/slip/match', json={**MARKET, "text": "Jalen Brunson\nOver 26.5 Points\nNikola Jokic\n25+ points\nJaylen Brown\nOver 20.5 PRA"})
    assert result.status_code == 200
    matches = result.json()["matches"]
    assert [m["candidate_ids"] for m in matches] == [[11], [22], []]
    assert "PRA" in matches[-1]["text"]


@pytest.mark.parametrize("prop", ["Under 26.5 points", "Over 25.5 points", "Over 26.5 rebounds", "26.5 points"])
def test_never_substitutes_a_different_line_side_or_stat(client, prop):
    result = client.post('/api/slip/match', json={**MARKET, "text": "Jalen Brunson\n" + prop}).json()
    assert result["matches"][0]["candidate_ids"] == []


def test_review_requires_confirmation_and_live_quote_identity(client):
    assert client.post('/api/slip/review', json={**MARKET, "legs": [11]}).status_code == 422
    assert client.post('/api/slip/review', json={**MARKET, "legs": [999], "confirmed": True}).status_code == 409
    assert client.post('/api/slip/review', json={**MARKET, "legs": [11, 11], "confirmed": True}).status_code == 422


def test_review_reports_weak_leg_removal_and_addition_tradeoff(client):
    result = client.post('/api/slip/review', json={**MARKET, "legs": [11, 22], "confirmed": True})
    assert result.status_code == 200
    body = result.json()
    assert body["legs"][0]["id"] == 11
    assert body["legs"][0]["assessment"] == "Consider removing"
    assert body["legs"][0]["projection"] == 28.5
    assert body["legs"][0]["without_chance_pct"] > body["chance_pct"]
    assert body["additions"][0]["id"] == 33
    assert body["additions"][0]["with_chance_pct"] < body["chance_pct"]


def png():
    data = io.BytesIO()
    Image.new('RGB', (400, 200), 'white').save(data, format='PNG')
    return data.getvalue()


def test_multiple_images_return_separate_editable_text(client, monkeypatch):
    monkeypatch.setattr(review, '_engine', lambda image: SimpleNamespace(txts=('Jalen Brunson', 'Over 26.5 Points'), scores=(.99, .65)))
    result = client.post('/api/slip/read', files=[('images', ('one.png', png(), 'image/png')), ('images', ('two.png', png(), 'image/png'))])
    assert result.status_code == 200
    assert len(result.json()['images']) == 2
    assert result.json()['images'][0]['low_confidence'] is True
    assert '26.5' in result.json()['images'][0]['text']


def test_upload_checks_actual_image_bytes_count_and_size(client, monkeypatch):
    monkeypatch.setattr(review, '_engine', lambda image: pytest.fail('Invalid image reached OCR'))
    assert client.post('/api/slip/read', files={'images': ('fake.png', b'not an image', 'image/png')}).status_code == 422
    assert client.post('/api/slip/read', files=[('images', (f'{n}.png', png(), 'image/png')) for n in range(6)]).status_code == 400
    monkeypatch.setattr(review, 'MAX_FILE_BYTES', 10)
    assert client.post('/api/slip/read', files={'images': ('big.png', png(), 'image/png')}).status_code == 413


def test_ocr_failure_does_not_expose_text_or_internal_paths(client, monkeypatch):
    def fail(image): raise RuntimeError('private filesystem path and account info')
    monkeypatch.setattr(review, '_engine', fail)
    response = client.post('/api/slip/read', files={'images': ('a.png', png(), 'image/png')})
    assert response.status_code == 503
    assert 'private' not in response.text


def test_a_bet_printed_on_the_players_own_line_ignores_the_lines_after_it(client):
    # Kalshi's layout; the players after Jokic are not on the board and name other stats
    text = "Nikola Jokic: 25+ points\nGS Warriors vs HOU Rockets\nSome Guard: 3+ threes\nSome Center: 4+ assists"
    matches = client.post('/api/slip/match', json={**MARKET, "text": text}).json()["matches"]
    assert [m["candidate_ids"] for m in matches] == [[22]]
