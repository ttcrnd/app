from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from review_app import deps
from review_app.jobs import Job, jobs, queue_job_log, run_pipeline
from domain.workflow import normalize_form_workflow

router = APIRouter(tags=["pipeline"])

@router.post("/api/run")
async def api_run(payload: dict) -> JSONResponse:
    repo = (payload.get("repo") or "").strip()
    if not repo:
        raise HTTPException(status_code=400, detail="Missing 'repo' field")
    payload_token = (payload.get("token") or "").strip()
    token_override = payload_token or None
    configured = deps.configured_token()
    effective_token = token_override or configured
    if not effective_token:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "token_required",
                "message": "GitHub token chybí. Zadej token pro tento běh, nebo nastav GITHUB_TOKEN na serveru.",
            },
        )

    jid = uuid.uuid4().hex
    job = Job(id=jid, repo=repo, token=token_override)
    jobs[jid] = job
    queue_job_log(job, "START", f"JOB queued id={jid} repo={repo}")

    # Start background task
    asyncio.create_task(run_pipeline(job))

    return JSONResponse(
        {
            "job_id": jid,
            "evaluation_id": jid,
            "status": job.status,
            "repo": repo,
        }
    )


@router.get("/api/status/{job_id}")
async def api_status(job_id: str) -> JSONResponse:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse(
        {
            "job_id": job.id,
            "repo": job.repo,
            "status": job.status,
            "return_code": job.return_code,
            "result_path": str(job.result_path) if job.result_path else None,
            "error": job.error,
        }
    )


@router.get("/api/events/{job_id}")
async def api_events(request: Request, job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        # Send buffered logs first
        for line in job.logs:
            yield {"event": "log", "data": line}

        # Then stream new lines until done or client disconnects
        while True:
            if await request.is_disconnected():
                break
            try:
                line = await asyncio.wait_for(job.queue.get(), timeout=1.0)
                if line == "[server] done":
                    # Include status snapshot
                    yield {
                        "event": "done",
                        "data": json.dumps(
                            {
                                "status": job.status,
                                "return_code": job.return_code,
                                "result_path": str(job.result_path) if job.result_path else None,
                                "error": job.error,
                            }
                        ),
                    }
                    break
                else:
                    yield {"event": "log", "data": line}
            except asyncio.TimeoutError:
                # Periodic heartbeat to keep the connection alive
                yield {"event": "ping", "data": ""}

    return EventSourceResponse(event_generator())


@router.get("/api/result/{job_id}")
async def api_result(job_id: str) -> JSONResponse:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("done", "error"):
        raise HTTPException(status_code=425, detail="Job not finished yet")
    if job.status == "error":
        raise HTTPException(status_code=500, detail=job.error or "Unknown error")
    if not job.result_path or not job.result_path.exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    try:
        data = json.loads(job.result_path.read_text(encoding="utf-8"))
        data = normalize_form_workflow(data, pipeline_mode=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read result: {e}") from e
    return JSONResponse(data)

