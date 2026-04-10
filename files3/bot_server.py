# =============================================================================
# bot/bot_server.py
# Bot HTTP Server — receives messages from Teams via Azure Bot Service
# =============================================================================
# Run with:
#   python bot/bot_server.py
# =============================================================================

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from aiohttp import web
from botbuilder.core import BotFrameworkAdapter, BotFrameworkAdapterSettings
from botbuilder.schema import Activity

from data.qvd_loader import ClaimsDataLoader, load_config
from data.text_chunker import dataframe_to_chunks
from ai.embeddings import ClaimsSearchEngine
from ai.llm import ClaimsLLM
from ai.rag_pipeline import RAGPipeline
from bot.teams_bot import ClaimsBot

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("claims.bot_server")

# ---------------------------------------------------------------------------
# Load config and initialise pipeline
# ---------------------------------------------------------------------------
logger.info("Loading config...")
config = load_config("config/config.yaml")
bot_cfg = config.get("teams_bot", {})

APP_ID     = bot_cfg.get("app_id", "")
APP_SECRET = bot_cfg.get("app_secret", "")

logger.info("Initialising RAG pipeline...")
loader = ClaimsDataLoader(config_path="config/config.yaml")
loader.load()

chunks = dataframe_to_chunks(
    loader.df,
    loader.col,
    chunk_size=config["data"]["chunk_size"],
)

engine = ClaimsSearchEngine(config)
engine.build(chunks)

llm      = ClaimsLLM(config)
pipeline = RAGPipeline(loader, engine, llm)

logger.info("RAG pipeline ready ✓")

# ---------------------------------------------------------------------------
# Bot Framework adapter
# ---------------------------------------------------------------------------
settings = BotFrameworkAdapterSettings(APP_ID, APP_SECRET)
adapter  = BotFrameworkAdapter(settings)
bot      = ClaimsBot(pipeline)


async def on_error(context, error):
    """Global error handler for the bot adapter."""
    logger.error(f"Bot adapter error: {error}")
    await context.send_activity("⚠️ An error occurred. Please try again.")


adapter.on_turn_error = on_error

# ---------------------------------------------------------------------------
# HTTP handler — Teams posts messages to /api/messages
# ---------------------------------------------------------------------------

async def messages(req: web.Request) -> web.Response:
    """
    Main webhook endpoint. Teams sends every user message here.
    The adapter authenticates it and passes it to the bot.
    """
    if req.content_type != "application/json":
        return web.Response(status=415, text="Unsupported Media Type")

    body     = await req.json()
    activity = Activity().deserialize(body)
    auth     = req.headers.get("Authorization", "")

    response = await adapter.process_activity(activity, auth, bot.on_turn)
    if response:
        return web.json_response(data=response.body, status=response.status)
    return web.Response(status=201)


# ---------------------------------------------------------------------------
# Start server
# ---------------------------------------------------------------------------
app = web.Application()
app.router.add_post("/api/messages", messages)

if __name__ == "__main__":
    logger.info("Starting Teams bot server on port 8000...")
    logger.info(f"Messaging endpoint: POST /api/messages")
    logger.info(f"App ID: {APP_ID[:8]}..." if APP_ID else "⚠️  No App ID set in config")
    web.run_app(app, host="0.0.0.0", port=8000)
