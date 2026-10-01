from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

from _web_js import read_web_js


def test_step2_question_card_hotovo_and_queue_markers():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = read_web_js(WEB)
    css = (WEB / "styles.css").read_text(encoding="utf-8")

    assert "K vyřízení" in js
    assert "goToNextTodoQuestion" in js
    assert "q-done-btn" in js
    assert "rating-segment" in js
    assert "q-note-hero" in js
    assert "q-actions-row" in js
    assert "Přidat" in js
    assert "q-auto-chip" in js
    assert "statusText = 'Potvrdit'" in js
    assert "statusText = 'Doplň'" in js
    assert "statusText = 'Hotovo'" in js
    assert "statusText = 'Čeká'" not in js
    assert "Navrženo automatem" not in js
    assert "Potvrdit hodnocení" not in js
    assert "queueMode" in js
    assert "q-extras" in js
    assert "Podklady" in js
    assert "syncExtrasSummary" in js
    assert "Stáhnout oficiální PDF" in html
    assert 'id="workFooter"' in html
    assert "disabled" in html.split('id="downloadPdfBtn"', 1)[1].split("</button>", 1)[0]

    assert "q-note-hero" in css
    assert "rating-segment" in css
    assert 'data-card-tone="review"' in css or "[data-card-tone=\"review\"]" in css
    assert ".q-auto-chip" in css
    assert ".q-actions-row" in css
    assert ".q-extras" in css
    assert ".work-footer" in css
