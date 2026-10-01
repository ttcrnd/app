from __future__ import annotations

import json
from typing import Any

from db.models import Evaluation

def evaluation_to_list_item(evaluation: Evaluation) -> dict[str, Any]:
    form_path = ""
    signed = False
    signed_at = ""
    for art in evaluation.artifacts or []:
        if art.kind == "form":
            form_path = art.path
        if art.kind == "signed_export":
            signed = True
    try:
        form_obj = json.loads(evaluation.form_json or "{}")
        meta = form_obj.get("meta") if isinstance(form_obj, dict) else {}
        if isinstance(meta, dict) and meta.get("signature"):
            signed = True
            signed_at = str(meta.get("signature", {}).get("signed_at") or "")
    except Exception:
        pass
    status = evaluation.status or "draft"
    return {
        "id": evaluation.id,
        "title": evaluation.title,
        "library": evaluation.repo,
        "repo": evaluation.repo,
        "ref": evaluation.ref,
        "status": status,
        "status_label": status_label_cs(status),
        "signed": signed,
        "signed_at": signed_at,
        "updated_at": evaluation.updated_at.isoformat() if evaluation.updated_at else "",
        "started_at": evaluation.started_at.isoformat() if evaluation.started_at else "",
        "completed_at": evaluation.completed_at.isoformat() if evaluation.completed_at else "",
        "path": form_path,
    }


def status_label_cs(status: str) -> str:
    mapping = {
        "draft": "Rozpracováno",
        "in_progress": "Rozpracováno",
        "completed": "Hotovo",
        "not_recommended": "Nedoporučeno",
    }
    return mapping.get(status, "Rozpracováno")

