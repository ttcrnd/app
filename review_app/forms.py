from __future__ import annotations

import json
import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from jsonschema import Draft7Validator

from review_app.paths import FORM_SCHEMA_PATH
from domain.scoring import calculate_summary
from domain.workflow import normalize_form_workflow

def calc_summary(form_sc: dict) -> dict:
    return calculate_summary(form_sc)


def schema_error_path(error: Any) -> str:
    path = "$"
    for part in list(getattr(error, "path", [])):
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def validate_and_prepare_form(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Neplatný požadavek: očekávám JSON objekt.")

    payload_looks_like_form = all(
        required_key in payload for required_key in ("title", "version", "language", "sections")
    )
    if "form" in payload and not payload_looks_like_form:
        form_candidate: Any = payload.get("form")
    else:
        form_candidate = payload
    if not isinstance(form_candidate, dict):
        raise HTTPException(
            status_code=400,
            detail="Neplatný formát: očekávám objekt formuláře nebo pole 'form'.",
        )

    form_obj = json.loads(json.dumps(form_candidate))
    form_obj = normalize_form_workflow(form_obj, pipeline_mode=False)

    if not FORM_SCHEMA_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="Server nemá dostupné validační schéma formuláře.",
        )

    try:
        schema = json.loads(FORM_SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = Draft7Validator(schema)
        errors = sorted(validator.iter_errors(form_obj), key=lambda err: list(err.path))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validace formuláře selhala: {e}") from e

    if errors:
        first_error = errors[0]
        path = schema_error_path(first_error)
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Soubor JSON neodpovídá očekávanému formátu hodnocení.",
                "path": path,
                "reason": first_error.message,
                "hint": "Zkontroluj uvedené pole a nahraj soubor znovu.",
            },
        )

    summary = calc_summary(form_obj)
    form_obj["summary"] = summary
    return form_obj


REPO_SLUG_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<name>[A-Za-z0-9_.-]+)$")


def clean_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def collect_pdf_meta_sources(form_dict: dict[str, Any]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    top_meta = form_dict.get("meta")
    if isinstance(top_meta, dict):
        sources.append(top_meta)
    sections = form_dict.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            sec_meta = section.get("meta")
            if isinstance(sec_meta, dict):
                sources.append(sec_meta)
    return sources


def pick_first_meta_value(sources: list[dict[str, Any]], keys: list[str]) -> str:
    for source in sources:
        for key in keys:
            value = clean_str(source.get(key))
            if value:
                return value
    return ""


def repo_slug_from_value(value: str) -> str:
    candidate = clean_str(value).rstrip("/")
    if not candidate:
        return ""
    if candidate.startswith("http://") or candidate.startswith("https://"):
        parsed = urlparse(candidate)
        host = parsed.netloc.lower()
        if host not in {"github.com", "www.github.com"}:
            return ""
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            return ""
        return f"{parts[0]}/{parts[1]}"
    match = REPO_SLUG_RE.match(candidate)
    if match:
        return f"{match.group('owner')}/{match.group('name')}"
    return ""


def resolve_pdf_identification(form_dict: dict[str, Any]) -> dict[str, str]:
    meta_sources = collect_pdf_meta_sources(form_dict)
    if not meta_sources:
        meta_sources = [{}]

    repo_raw = pick_first_meta_value(
        meta_sources, ["repo", "repository", "repository_full_name", "repository_name"]
    )
    url_raw = pick_first_meta_value(
        meta_sources, ["url", "html_url", "repository_url", "homepage", "repo_url"]
    )
    repo_slug = repo_slug_from_value(repo_raw) or repo_slug_from_value(url_raw)

    name = pick_first_meta_value(
        meta_sources, ["name", "library_name", "project_name", "package_name"]
    )
    if not name and repo_slug:
        name = repo_slug.split("/", 1)[1]

    lib_type = pick_first_meta_value(meta_sources, ["type", "library_type"])

    publisher = pick_first_meta_value(
        meta_sources, ["publisher", "owner", "maintainer", "organization", "vendor"]
    )
    if not publisher and repo_slug:
        publisher = repo_slug.split("/", 1)[0]

    url = url_raw
    if not url:
        if repo_raw.startswith("http://") or repo_raw.startswith("https://"):
            url = repo_raw
        elif repo_slug:
            url = f"https://github.com/{repo_slug}"

    version = pick_first_meta_value(
        meta_sources,
        [
            "version",
            "evaluated_repo_version",
            "effective_ref",
            "requested_ref",
            "tag",
            "default_branch",
        ],
    )

    assessment_date = pick_first_meta_value(
        meta_sources,
        ["assessment_date", "evaluation_date", "datum_hodnoceni", "started_at", "finished_at"],
    )
    if assessment_date and len(assessment_date) >= 10 and assessment_date[4] == "-":
        assessment_date = assessment_date[:10]
    elif not assessment_date:
        assessment_date = date.today().isoformat()
    else:
        assessment_date = assessment_date[:10] if len(assessment_date) >= 10 else date.today().isoformat()

    return {
        "Název knihovny": name,
        "Typ knihovny": lib_type,
        "Správce/vydavatel": publisher,
        "URL": url,
        "Verze knihovny": version,
        "Datum hodnocení": assessment_date,
    }

