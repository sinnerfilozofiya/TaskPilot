"""Cursor CLI status and verify: check provider and test CLI from the server."""
import asyncio

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/status")
async def cursor_status(request: Request):
    """Return whether the summarization provider is Cursor (for UI hints)."""
    from app.config import config
    provider_is_cursor = config.LLM_PROVIDER.lower() == "cursor"
    return {"provider_is_cursor": provider_is_cursor}


@router.get("/verify")
async def cursor_verify(request: Request):
    """Run a quick Cursor CLI check (cursor --version) to verify CLI is installed. Returns ok + message or error."""
    from app.config import config
    from app.services.llm.cursor_cli_provider import CursorCLIProvider

    if config.LLM_PROVIDER.lower() != "cursor":
        return {"ok": False, "error": "LLM_PROVIDER is not set to cursor"}

    provider = CursorCLIProvider()
    try:
        version = await asyncio.wait_for(provider.verify_cli_available(timeout=5.0), timeout=6.0)
        return {"ok": True, "message": f"Cursor CLI is available. {version}"}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Cursor CLI version check timed out after 5 seconds."}
    except FileNotFoundError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)}"}
