from contextlib import asynccontextmanager

from fastapi import FastAPI

from open_brain.api.auth import verify_access_key
from open_brain.api.routes import router as api_router
from open_brain.api.slack import router as slack_router
from open_brain.db.session import close_pool, get_pool
from open_brain.mcp.server import mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize DB pool
    await get_pool()
    yield
    # Shutdown: close DB pool
    await close_pool()


app = FastAPI(
    title="Open Brain",
    description="Personal knowledge management with semantic search and MCP",
    lifespan=lifespan,
)

# REST API routes (auth handled by router dependency)
app.include_router(api_router)
app.include_router(slack_router)

# Mount MCP server at /mcp
mcp_app = mcp.streamable_http_app()
app.mount("/mcp", mcp_app)


@app.get("/health")
async def health():
    """Health check endpoint."""
    try:
        pool = await get_pool()
        count = await pool.fetchval("SELECT COUNT(*) FROM thoughts")
        return {"status": "healthy", "thoughts_count": count}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
