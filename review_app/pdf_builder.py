from __future__ import annotations

import io
import logging
import os
from pathlib import Path

from fastapi import HTTPException

from review_app.forms import resolve_pdf_identification
from review_app.paths import FONTS_DIR, ROOT

logger = logging.getLogger("review.pdf")

def build_pdf(form_obj: dict) -> bytes:
    try:
        # Lazy import to keep server lightweight if PDF isn't used
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"PDF backend not available: {e}") from e

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Formulář v1.0: Hodnocení open-source knihovny",
    )
    styles = getSampleStyleSheet()

    # Unicode font setup: prefer env var, then ./fonts, then common system font folders.
    normal_font = "Helvetica"
    bold_font = "Helvetica-Bold"
    try:

        def try_register(path: Path) -> bool:
            if path and path.exists() and path.is_file():
                pdfmetrics.registerFont(TTFont("UI", str(path)))
                return True
            return False

        # 1) Explicit override via env var
        env_font = os.environ.get("REVIEW_PDF_FONT", "").strip()
        if env_font and try_register(Path(env_font)):
            normal_font = bold_font = "UI"
            logger.info("[pdf] Using font from REVIEW_PDF_FONT: %s", Path(env_font).name)
        else:
            # 2) Project fonts directory
            fonts_dir = FONTS_DIR
            if not fonts_dir.exists():
                fonts_dir = ROOT / "fonts"  # legacy layout
            candidates = (
                "ChocolateClassicalSans-Regular.ttf",
                "DejaVuSans.ttf",
                "NotoSans-Regular.ttf",
                "LiberationSans-Regular.ttf",
                "Arial.ttf",
                "Arial Unicode.ttf",
                "FreeSans.ttf",
                "Roboto-Regular.ttf",
                "SourceSans3-Regular.ttf",
            )
            chosen = False
            for fname in candidates:
                if try_register(fonts_dir / fname):
                    normal_font = bold_font = "UI"
                    logger.info("[pdf] Using font: %s", fname)
                    chosen = True
                    break
            # 3) System font locations (macOS/Linux)
            if not chosen:
                sys_dirs = [
                    Path.home() / "Library/Fonts",
                    Path("/Library/Fonts"),
                    Path("/System/Library/Fonts"),
                    Path("/System/Library/Fonts/Supplemental"),
                    Path("/usr/share/fonts"),
                    Path("/usr/local/share/fonts"),
                    Path.home() / ".local/share/fonts",
                ]
                found = None
                for d in sys_dirs:
                    for fname in candidates:
                        p = d / fname
                        if try_register(p):
                            found = p
                            break
                    if found:
                        break
                if found:
                    normal_font = bold_font = "UI"
                    logger.info("[pdf] Using system font: %s", found)
        if normal_font == "Helvetica":
            logger.warning(
                "[pdf] No Unicode TTF found. Set REVIEW_PDF_FONT or add e.g. DejaVuSans.ttf to ./assets/fonts for Czech diacritics."
            )
    except Exception as e:
        logger.warning("[pdf] Font registration failed; using Helvetica: %s", e)
    style_title = ParagraphStyle(
        "TitleCZ",
        parent=styles["Title"],
        fontName=bold_font,
        fontSize=18,
        spaceAfter=8,
    )
    style_h2 = ParagraphStyle(
        "H2CZ",
        parent=styles["Heading2"],
        fontName=bold_font,
        fontSize=12,
        spaceBefore=8,
        spaceAfter=4,
    )
    style_kv_label = ParagraphStyle(
        "KVLabel",
        parent=styles["Normal"],
        fontName=bold_font,
        fontSize=10,
        leading=12,
    )
    style_kv_value = ParagraphStyle(
        "KVValue",
        parent=styles["Normal"],
        fontName=normal_font,
        fontSize=10,
        leading=12,
    )
    style_q_text = ParagraphStyle(
        "QText",
        parent=styles["Normal"],
        fontName=normal_font,
        fontSize=10.5,
        leading=13.5,
        spaceBefore=6,
        spaceAfter=3,
    )
    style_sec = ParagraphStyle(
        "SecCZ",
        parent=styles.get("Heading3", styles["Heading2"]),
        fontName=bold_font,
        fontSize=11,
        spaceBefore=8,
        spaceAfter=2,
    )
    style_opts = ParagraphStyle(
        "QOpts",
        parent=styles["Normal"],
        fontName=normal_font,
        fontSize=10,
        leading=13,
        leftIndent=8,
        spaceAfter=2,
    )

    def _checkbox_line(rating: str, *, official: bool) -> str:
        r = (rating or "").strip().lower()

        def box(opt: str) -> str:
            return "☑" if r == opt else "☐"

        if official:
            # Formulář v1.0: tři hodnoty; nehodnoceno se v odevzdávce nezobrazuje jako volba.
            line = (
                f"{box('splňuje')} Splňuje    "
                f"{box('částečně splňuje')} Částečně splňuje    "
                f"{box('nesplňuje')} Nesplňuje"
            )
            if r in {"", "nehodnoceno"}:
                line += "    (zatím nehodnoceno — doplnit před odevzdáním)"
            return line
        return (
            f"{box('nehodnoceno')} nehodnoceno    "
            f"{box('splňuje')} splňuje    "
            f"{box('částečně splňuje')} částečně splňuje    "
            f"{box('nesplňuje')} nesplňuje"
        )

    def _is_appendix_section(sec: dict) -> bool:
        stype = str(sec.get("type") or "").strip().lower()
        return stype in {"appendix", "informational", "info"}

    def _escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _append_question_block(q: dict, idx: int, *, official: bool) -> None:
        qtext = str(q.get("text") or "").strip()
        rating = str(q.get("rating") or "").strip()
        if not qtext:
            return
        story.append(Paragraph(f"{idx}. {_escape(qtext)}", style_q_text))
        story.append(Paragraph(_checkbox_line(rating, official=official), style_opts))
        note = str(q.get("note") or "").strip()
        if note:
            story.append(Paragraph(f"<b>Poznámka:</b> {_escape(note)}", style_note))
        evidence = q.get("evidence")
        if isinstance(evidence, list):
            evidence_text = "\n".join(str(x).strip() for x in evidence if str(x).strip())
        else:
            evidence_text = str(evidence or "").strip()
        if evidence_text:
            for i, line in enumerate(evidence_text.splitlines()):
                line = line.strip()
                if not line:
                    continue
                prefix = "<b>Důkaz:</b> " if i == 0 else ""
                story.append(Paragraph(prefix + _escape(line), style_note))

    style_note = ParagraphStyle(
        "QNote",
        parent=styles["Normal"],
        fontName=normal_font,
        fontSize=9,
        leading=12,
        leftIndent=8,
        spaceAfter=2,
    )

    story = []
    story.append(Paragraph("Formulář v1.0: Hodnocení open-source knihovny", style_title))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Identifikace", style_h2))

    kv = resolve_pdf_identification(form_obj)
    for k in [
        "Název knihovny",
        "Typ knihovny",
        "Správce/vydavatel",
        "URL",
        "Verze knihovny",
        "Datum hodnocení",
    ]:
        story.append(Paragraph(k + ":", style_kv_label))
        story.append(Paragraph(str(kv.get(k, "")) or "—", style_kv_value))
        story.append(Spacer(1, 2))

    sections = [s for s in (form_obj.get("sections") or []) if isinstance(s, dict)]
    official_sections = [s for s in sections if not _is_appendix_section(s)]
    appendix_sections = [s for s in sections if _is_appendix_section(s)]

    story.append(Spacer(1, 6))
    story.append(Paragraph("Oficiální formulář (sekce metodiky 6.1–6.5)", style_h2))
    for si, sec in enumerate(official_sections):
        qs = sec.get("questions", []) if isinstance(sec.get("questions"), list) else []
        if not qs:
            continue
        sec_title = str(sec.get("title") or "").strip()
        sec_label = sec_title or f"Sekce {sec.get('id') or (si + 1)}"
        story.append(Paragraph(_escape(sec_label), style_sec))
        for idx, q in enumerate(qs, start=1):
            if isinstance(q, dict):
                _append_question_block(q, idx, official=True)
        story.append(Spacer(1, 4))

    if appendix_sections:
        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                "Příloha (mimo formulář v1.0)",
                style_h2,
            )
        )
        for si, sec in enumerate(appendix_sections):
            qs = sec.get("questions", []) if isinstance(sec.get("questions"), list) else []
            if not qs:
                continue
            sec_title = str(sec.get("title") or "").strip()
            sec_label = sec_title or f"Příloha {sec.get('id') or (si + 1)}"
            story.append(Paragraph(_escape(sec_label), style_sec))
            for idx, q in enumerate(qs, start=1):
                if isinstance(q, dict):
                    _append_question_block(q, idx, official=False)
            story.append(Spacer(1, 4))

    doc.build(story)
    return buf.getvalue()

