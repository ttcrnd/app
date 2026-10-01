from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from review_app import deps
from review_app.paths import ROOT


@dataclass
class Job:
    id: str
    repo: str
    status: str = "queued"  # queued | running | done | error
    return_code: int | None = None
    result_path: Path | None = None
    error: str | None = None
    logs: list[str] = field(default_factory=list)
    queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    token: str | None = None


jobs: dict[str, Job] = {}

AGG_DONE_RE = re.compile(r"Aggregated form:\s*(.+)$")


def queue_job_log(job: Job, level: str, message: str) -> None:
    line = f"[{level}] [server] {message}"
    job.logs.append(line)
    job.queue.put_nowait(line)


async def run_pipeline(job: Job) -> None:
    job.status = "running"
    queue_job_log(job, "START", f"JOB running id={job.id} repo={job.repo}")
    py = sys.executable
    cmd = [py, str(ROOT / "run_all.py"), job.repo, "--run-id", job.id]
    queue_job_log(
        job,
        "INFO",
        f"JOB spawning subprocess command={cmd[0]} run_all.py {job.repo} --run-id {job.id}",
    )

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env["REVIEW_RUN_ID"] = job.id
    token_value = job.token or deps.configured_token()
    if token_value:
        env["GITHUB_TOKEN"] = token_value
        env["GH_TOKEN"] = token_value
    job.token = None

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    queue_job_log(job, "INFO", f"JOB subprocess started pid={proc.pid}")

    assert proc.stdout is not None
    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\n")
            job.logs.append(text)
            await job.queue.put(text)
            m = AGG_DONE_RE.search(text)
            if m:
                p = Path(m.group(1).strip())
                if not p.is_absolute():
                    p = (ROOT / p).resolve()
                job.result_path = p
    except Exception as e:
        job.error = f"streaming error: {e}"
        job.status = "error"
        queue_job_log(job, "WARN", f"JOB streaming error: {job.error}")
        await job.queue.put("[server] done")
        return

    rc = await proc.wait()
    job.return_code = rc
    if rc == 0:
        job.status = "done"
        queue_job_log(
            job,
            "DONE",
            f"JOB completed successfully rc=0 result={job.result_path if job.result_path else '-'}",
        )
    else:
        job.status = "error"
        if not job.error:
            job.error = f"pipeline exited with code {rc}"
        queue_job_log(job, "WARN", f"JOB completed with error rc={rc} message={job.error}")

    await job.queue.put("[server] done")
