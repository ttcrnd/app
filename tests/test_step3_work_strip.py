from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

from _web_js import read_web_js


def test_step3_work_strip_pdf_confidence_and_toast():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    js = read_web_js(WEB)
    css = (WEB / "styles.css").read_text(encoding="utf-8")

    assert 'id="workStats"' in html
    assert 'id="workRemaining"' in html
    assert 'id="workMustOpen"' in html
    assert 'id="workLowConf"' in html
    assert 'id="workFooter"' in html
    assert "Oficiální PDF ještě nejde stáhnout" in html
    assert 'id="pdfReadiness"' in html
    assert 'id="pdfMissingList"' in html
    assert 'id="appToast"' in html
    assert "Interní pomůcka" in html
    assert "Overall score" not in html
    assert "Grade:" not in html.split('id="viewWork"', 1)[1].split('id="pipelineDrawer"', 1)[0]

    # Primary strip actions are only ⋯; complete/PDF live in footer
    strip = html.split('class="work-strip"', 1)[1].split('id="collectionBanner"', 1)[0]
    assert 'id="completeEvalBtn"' not in strip
    assert 'id="downloadPdfBtn"' not in strip
    assert "PDF koncept" in strip
    assert 'id="workFooter"' in html
    footer = html.split('id="workFooter"', 1)[1].split('id="techPanel"', 1)[0]
    assert 'id="completeEvalBtn"' in footer
    assert 'id="downloadPdfBtn"' in footer

    assert "countRemainingWork" in js
    assert "renderPdfReadiness" in js
    assert "pdf-missing-chip" in js
    assert "syncOfficialPdfButton" in js
    assert "syncWorkFooter" in js
    assert "jumpToFlaggedQuestion" in js
    assert "jumpToQuestionById" in js
    assert "resolveQuestionConfidence" in js
    assert "Nízká jistota automatu" in js
    assert "Nasbíráno. Zbývá" in js
    assert "Interní skóre:" in js
    assert "Overall score:" not in js
    assert "Cutoffs (must-have):" not in js
    assert "queueMode = 'all'" in js or "queueMode: 'all'" in js
    assert "queueMode = 'todo'" in js  # still used by „K vyřízení“ / Další
    assert "Filtrovat…" in js
    assert "details-toolbar__more" in js
    assert "section-remaining" in js
    assert "Zbývá" in js

    assert ".work-stats" in css
    assert ".work-footer" in css
    assert ".pdf-readiness" in css
    assert ".q-confidence" in css
    assert ".q-auto-chip" in css
    assert '[data-card-tone="review"]' in css
    assert ".app-toast" in css
    assert ".details-toolbar__more" in css
    assert ".section-remaining" in css
