from __future__ import annotations

from pathlib import Path

WEB_DIR = Path(__file__).resolve().parents[1] / "web"


def read_web_js(web_dir: Path | None = None) -> str:
    """Concatenate all frontend JS so marker tests survive ES-module splits."""
    root = web_dir or WEB_DIR
    chunks: list[str] = []
    app = root / "app.js"
    if app.exists():
        chunks.append(app.read_text(encoding="utf-8"))
    js_dir = root / "js"
    if js_dir.is_dir():
        for path in sorted(js_dir.rglob("*.js")):
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)
