from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "web" / "index.html"


def test_step1_home_work_information_architecture():
    html = INDEX.read_text(encoding="utf-8")

    assert "<title>NÚKIB OSS reviewer</title>" in html
    assert "Review Pipeline UI" not in html

    assert 'id="viewHome"' in html
    assert 'id="viewWork"' in html
    assert 'id="navHomeBtn"' in html
    assert 'id="navWorkBtn"' in html
    assert 'id="libraryList"' in html
    assert 'id="homeEmpty"' in html
    assert "Spusť nové hodnocení" in html
    assert "Začni ukázkou OpenSSL" not in html
    assert 'id="newEvalPanel"' in html
    assert 'id="newEvalBtn"' in html

    assert "Stáhnout oficiální PDF" in html
    assert "PDF koncept" in html
    assert 'id="moreMenu"' in html
    assert "Stáhnout JSON" in html
    assert 'id="techPanel"' in html

    assert 'id="pipelineDrawer"' in html
    assert 'id="pipelineFab"' in html

    # Domů must not embed the live log/json as primary chrome
    home_chunk = html.split('id="viewHome"', 1)[1].split('id="viewWork"', 1)[0]
    assert 'id="log"' not in home_chunk
    assert 'id="json"' not in home_chunk
    assert "Finální výstupní soubor" not in home_chunk
