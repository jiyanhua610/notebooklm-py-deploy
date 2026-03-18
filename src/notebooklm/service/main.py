"""CLI entrypoint for the NotebookLM PDF service."""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run("notebooklm.service.app:create_app", factory=True, host="0.0.0.0", port=8000)
