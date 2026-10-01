from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from db.repository import (
    add_audit,
    can_edit_evaluation,
    complete_evaluation,
    delete_evaluation,
    get_evaluation,
    list_evaluations,
    rating_diff_against_previous,
    save_evaluation,
    sign_evaluation,
)
from review_app.deps import (
    db_session,
    ensure_drafts_dir,
    request_has_pilot_session,
    session_from_request,
)
from review_app.paths import ROOT, TERMINAL_EVAL_STATUSES
from auth.pilot import (
    PILOT_USER_ID,
    auth_required,
    pilot_code_enabled,
    role_can_access_all_evaluations,
    role_can_write,
)

router = APIRouter(tags=["evaluations"])

@router.post("/api/evaluations/{evaluation_id}/complete")
@router.post("/api/drafts/{evaluation_id}/complete")
async def api_complete_evaluation(evaluation_id: str, payload: dict) -> JSONResponse:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    safe = "".join(ch for ch in evaluation_id if ch.isalnum() or ch in {"-", "_"})
    if not safe or safe != evaluation_id:
        raise HTTPException(status_code=400, detail="Neplatné ID hodnocení")
    outcome = str(payload.get("outcome") or payload.get("status") or "").strip()
    note = str(payload.get("note") or payload.get("completion_note") or "").strip()
    session = db_session()
    try:
        evaluation = complete_evaluation(
            session,
            evaluation_id=safe,
            outcome=outcome,
            note=note,
        )
        session.commit()
        return JSONResponse(
            {
                "id": evaluation.id,
                "status": evaluation.status,
                "status_label": {
                    "completed": "Hotovo",
                    "not_recommended": "Nedoporučeno",
                }.get(evaluation.status or "", evaluation.status),
                "completed_at": (
                    evaluation.completed_at.isoformat() if evaluation.completed_at else ""
                ),
            }
        )
    except KeyError as e:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Dokončení selhalo: {e}") from e
    finally:
        session.close()


@router.post("/api/evaluations/{evaluation_id}/sign")
@router.post("/api/drafts/{evaluation_id}/sign")
async def api_sign_evaluation(evaluation_id: str) -> JSONResponse:
    safe = "".join(ch for ch in evaluation_id if ch.isalnum() or ch in {"-", "_"})
    if not safe or safe != evaluation_id:
        raise HTTPException(status_code=400, detail="Neplatné ID hodnocení")
    session = db_session()
    try:
        body = sign_evaluation(session, evaluation_id=safe)
        session.commit()
        return JSONResponse(
            {
                "id": body["id"],
                "signed": True,
                "sig": body["sig"],
                "path": body["path"],
                "message": "Export podepsán (Ed25519). Hodnocení zůstává uložené.",
            }
        )
    except KeyError as e:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        session.rollback()
        # Signing failure must not imply the evaluation was lost.
        raise HTTPException(
            status_code=500,
            detail=f"Podpis selhal (hodnocení zůstalo uložené): {e}",
        ) from e
    finally:
        session.close()


@router.get("/api/evaluations/{evaluation_id}/signed-export")
@router.get("/api/drafts/{evaluation_id}/signed-export")
async def api_get_signed_export(evaluation_id: str, request: Request) -> JSONResponse:
    from db.repos import common as repos_common

    safe = "".join(ch for ch in evaluation_id if ch.isalnum() or ch in {"-", "_"})
    if not safe or safe != evaluation_id:
        raise HTTPException(status_code=400, detail="Neplatné ID hodnocení")
    session = db_session()
    try:
        evaluation = get_evaluation(session, safe)
        if not evaluation:
            raise HTTPException(status_code=404, detail="Hodnocení nenalezeno")
        status = evaluation.status or "draft"
        if (
            pilot_code_enabled(ROOT)
            and status not in TERMINAL_EVAL_STATUSES
            and not request_has_pilot_session(request)
        ):
            raise HTTPException(status_code=401, detail="auth_required")

        signed_path = None
        for art in evaluation.artifacts or []:
            if art.kind == "signed_export" and art.path:
                candidate = Path(art.path)
                if not candidate.is_absolute():
                    candidate = ROOT / art.path
                if candidate.exists():
                    signed_path = candidate
                    break
        if signed_path is None:
            fallback = repos_common.ARTIFACTS_DIR / evaluation.id / "signed_export.json"
            if fallback.exists():
                signed_path = fallback

        if signed_path is not None:
            data = json.loads(signed_path.read_text(encoding="utf-8"))
            return JSONResponse(data)

        try:
            form_obj = json.loads(evaluation.form_json or "{}")
        except Exception:
            form_obj = {}
        meta = form_obj.get("meta") if isinstance(form_obj, dict) else {}
        sig = meta.get("signature") if isinstance(meta, dict) else None
        if not isinstance(sig, dict):
            raise HTTPException(status_code=404, detail="Podepsaný export neexistuje")
        from services.signing import strip_volatile

        payload = strip_volatile(form_obj)
        if isinstance(payload.get("meta"), dict):
            payload["meta"].pop("signature", None)
            payload["meta"].pop("signed", None)
        return JSONResponse({"payload": payload, "sig": sig})
    finally:
        session.close()


@router.post("/api/evaluations/verify")
async def api_verify_signed_export(payload: dict) -> JSONResponse:
    from services.signing import verify_signed_export

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    wrapper = payload.get("wrapper") if isinstance(payload.get("wrapper"), dict) else payload
    public_pem = payload.get("public_key_pem")
    try:
        result = verify_signed_export(
            wrapper,
            public_key_pem=str(public_pem) if public_pem else None,
            root=ROOT,
        )
        return JSONResponse(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/api/signing/public-key")
async def api_signing_public_key() -> JSONResponse:
    from services.signing import public_key_info

    return JSONResponse(public_key_info(ROOT))


@router.get("/api/evaluations/{evaluation_id}/diff-previous")
@router.get("/api/drafts/{evaluation_id}/diff-previous")
async def api_diff_previous(evaluation_id: str, request: Request) -> JSONResponse:
    safe = "".join(ch for ch in evaluation_id if ch.isalnum() or ch in {"-", "_"})
    if not safe or safe != evaluation_id:
        raise HTTPException(status_code=400, detail="Neplatné ID hodnocení")
    session = db_session()
    try:
        evaluation = get_evaluation(session, safe)
        if not evaluation:
            raise HTTPException(status_code=404, detail="Hodnocení nenalezeno")
        sess = session_from_request(request)
        status = evaluation.status or "draft"
        if status not in TERMINAL_EVAL_STATUSES:
            if auth_required(ROOT) and not sess:
                raise HTTPException(status_code=401, detail="Vyžaduje přihlášení")
        return JSONResponse(rating_diff_against_previous(session, evaluation_id=safe))
    except KeyError:
        raise HTTPException(status_code=404, detail="Hodnocení nenalezeno") from None
    finally:
        session.close()


@router.get("/api/drafts")
@router.get("/api/evaluations")
async def api_list_drafts(request: Request) -> JSONResponse:
    sess = session_from_request(request)
    session = db_session()
    try:
        include_all = bool(sess and role_can_access_all_evaluations(sess.role))
        owner = None if include_all else (sess.user_id if sess else None)
        items = list_evaluations(session, limit=50, owner_user_id=owner, include_all=include_all)
        return JSONResponse({"drafts": items, "evaluations": items})
    finally:
        session.close()


@router.get("/api/drafts/{draft_id}")
@router.get("/api/evaluations/{draft_id}")
async def api_get_draft(draft_id: str, request: Request) -> JSONResponse:
    safe = "".join(ch for ch in draft_id if ch.isalnum() or ch in {"-", "_"})
    if not safe or safe != draft_id:
        raise HTTPException(status_code=400, detail="Neplatné ID hodnocení")
    session = db_session()
    try:
        evaluation = get_evaluation(session, safe)
        if not evaluation:
            # Legacy file fallback during transition
            path = ensure_drafts_dir() / f"{safe}.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                save_evaluation(session, evaluation_id=safe, form_obj=data)
                session.commit()
                evaluation = get_evaluation(session, safe)
        if not evaluation:
            raise HTTPException(status_code=404, detail="Hodnocení nenalezeno")
        status = evaluation.status or "draft"
        sess = session_from_request(request)
        if status not in TERMINAL_EVAL_STATUSES:
            if auth_required(ROOT) and not sess:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "code": "auth_required",
                        "message": "Rozpracované hodnocení vyžaduje přihlášení.",
                    },
                )
            if sess and not role_can_access_all_evaluations(sess.role):
                owner = evaluation.owner_user_id or "pilot"
                if sess.user_id != owner and not role_can_write(sess.role):
                    raise HTTPException(status_code=403, detail="Cizí hodnocení (D11)")
                if sess.role == "reviewer" and sess.user_id != owner:
                    raise HTTPException(
                        status_code=403,
                        detail="Cizí rozpracované hodnocení — jen vlastník nebo admin (D11).",
                    )
        elif auth_required(ROOT) and not sess and status not in TERMINAL_EVAL_STATUSES:
            raise HTTPException(status_code=401, detail="auth_required")
        try:
            form_data = json.loads(evaluation.form_json or "{}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Nelze načíst hodnocení: {e}") from e
        return JSONResponse(
            {
                "id": evaluation.id,
                "title": evaluation.title,
                "status": status,
                "library": evaluation.repo,
                "ref": evaluation.ref,
                "form": form_data,
            }
        )
    finally:
        session.close()


@router.post("/api/drafts")
@router.post("/api/evaluations")
async def api_save_draft(request: Request, payload: dict) -> JSONResponse:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    form_obj = payload.get("form") if isinstance(payload.get("form"), dict) else payload
    if not isinstance(form_obj, dict):
        raise HTTPException(status_code=400, detail="Očekáván formulář JSON")

    sess = session_from_request(request)
    if sess and not role_can_write(sess.role):
        raise HTTPException(status_code=403, detail="Role viewer nemůže ukládat")

    draft_id = str(payload.get("id") or payload.get("evaluation_id") or "").strip() or None
    session = db_session()
    try:
        if draft_id:
            existing = get_evaluation(session, draft_id)
            if (
                existing
                and sess
                and not can_edit_evaluation(existing, user_id=sess.user_id, role=sess.role)
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Cizí hodnocení nelze upravit (D11).",
                )
        owner = sess.user_id if sess else PILOT_USER_ID
        _evaluation, body = save_evaluation(
            session,
            evaluation_id=draft_id,
            form_obj=form_obj,
            title_fallback=str(payload.get("title") or ""),
            owner_user_id=owner,
        )
        session.commit()
        return JSONResponse(body)
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Uložení selhalo: {e}") from e
    finally:
        session.close()


@router.delete("/api/evaluations/{evaluation_id}")
@router.delete("/api/drafts/{evaluation_id}")
async def api_delete_evaluation(evaluation_id: str, request: Request) -> JSONResponse:
    sess = session_from_request(request)
    if not sess or not role_can_access_all_evaluations(sess.role):
        raise HTTPException(status_code=403, detail="Mazání hodnocení jen pro admin")
    safe = "".join(ch for ch in evaluation_id if ch.isalnum() or ch in {"-", "_"})
    session = db_session()
    try:
        delete_evaluation(session, safe)
        add_audit(
            session,
            event_type="evaluation_deleted",
            message=f"Smazáno hodnocení {safe}",
            actor_user_id=sess.user_id,
            payload={"evaluation_id": safe},
        )
        session.commit()
        return JSONResponse({"ok": True, "deleted": safe})
    except KeyError as e:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    finally:
        session.close()

