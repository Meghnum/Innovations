# =============================================================================
# bot/bot_server.py
# Bot HTTP Server — receives messages from Teams via Azure Bot Service
# Uses direct HTTP token fetch (tenant-specific) to avoid SDK auth issues
# =============================================================================
# Run with:
#   python bot/bot_server.py
# =============================================================================

import sys, json, logging, asyncio, re, time
import aiohttp
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from aiohttp import web
from data.qvd_loader import ClaimsDataLoader, load_config
from data.text_chunker import dataframe_to_chunks
from ai.embeddings import ClaimsSearchEngine
from ai.llm import ClaimsLLM
from ai.rag_pipeline import RAGPipeline
from bot.adaptive_cards import (
    aggregation_card, lookup_card, search_card,
    error_card, help_card, status_card,
)

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
CONFIG_PATH = str(Path(__file__).parent.parent / "config" / "config.yaml")
config  = load_config(CONFIG_PATH)
bot_cfg = config.get("teams_bot", {})

APP_ID     = bot_cfg.get("app_id", "")
APP_SECRET = bot_cfg.get("app_secret", "")
TENANT_ID  = bot_cfg.get("tenant_id", "")

logger.info(f"App ID    : {APP_ID}")
logger.info(f"Tenant ID : {TENANT_ID}")
logger.info(f"Secret set: {'Yes' if APP_SECRET else 'No'}")

logger.info("Initialising RAG pipeline...")
loader = ClaimsDataLoader(config_path=CONFIG_PATH)
loader.load()
chunks = dataframe_to_chunks(loader.df, loader.col, chunk_size=config["data"]["chunk_size"])
engine = ClaimsSearchEngine(config)
engine.build(chunks)
llm      = ClaimsLLM(config)
pipeline = RAGPipeline(loader, engine, llm)
logger.info("RAG pipeline ready ✓")

# ---------------------------------------------------------------------------
# Token management — tenant-specific URL bypasses Single/Multi tenant issues
# ---------------------------------------------------------------------------
_token_cache = {"token": None, "expires_at": 0}


async def get_access_token() -> str:
    """Fetch OAuth token using tenant-specific endpoint."""
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": APP_ID,
        "client_secret": APP_SECRET,
        "scope": "https://api.botframework.com/.default",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as resp:
            result = await resp.json()
            if "access_token" not in result:
                logger.error(f"Token error: {result}")
                raise PermissionError(f"Failed to get token: {result}")
            _token_cache["token"] = result["access_token"]
            _token_cache["expires_at"] = time.time() + result.get("expires_in", 3600)
            logger.info("Access token obtained ✓")
            return _token_cache["token"]


# ---------------------------------------------------------------------------
# Reply helpers — support both plain text and Adaptive Cards
# ---------------------------------------------------------------------------

async def send_reply(service_url, conversation_id, activity_id, text):
    """Send a plain markdown text reply."""
    token = await get_access_token()
    url = f"{service_url}v3/conversations/{conversation_id}/activities/{activity_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"type": "message", "text": text, "textFormat": "markdown"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                logger.error(f"Reply failed {resp.status}: {body}")
            else:
                logger.info("Reply sent successfully ✓")


async def send_card_reply(service_url, conversation_id, activity_id, card):
    """Send an Adaptive Card reply."""
    token = await get_access_token()
    url = f"{service_url}v3/conversations/{conversation_id}/activities/{activity_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # card from adaptive_cards.py already has {"type":"message","attachments":[...]}
    payload = card
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                logger.error(f"Card reply failed {resp.status}: {body}")
            else:
                logger.info("Card reply sent successfully ✓")


# ---------------------------------------------------------------------------
# Message handler
# ---------------------------------------------------------------------------

async def handle_message(activity):
    """Process an incoming Teams message and send a reply."""
    text = re.sub(r'<at>.*?</at>', '', activity.get("text", "")).strip()
    service_url = activity.get("serviceUrl", "")
    conversation_id = activity.get("conversation", {}).get("id", "")
    activity_id = activity.get("id", "")

    logger.info(f"Message received: '{text}'")

    # --- Help / greeting ---
    if not text or text.lower() in ["hi", "hello", "hey", "help"]:
        card = help_card()
        await send_card_reply(service_url, conversation_id, activity_id, card)
        return

    # --- Status command ---
    if text.lower() in ["status", "stats", "summary"]:
        card = status_card(pipeline.loader.summary, True)
        await send_card_reply(service_url, conversation_id, activity_id, card)
        return

    # --- Refresh command ---
    if text.lower() in ["refresh", "reload"]:
        pipeline.rebuild()
        await send_reply(service_url, conversation_id, activity_id,
                         "✅ Data refreshed and search index rebuilt.")
        return

    # --- Process question through RAG pipeline ---
    try:
        start = time.time()
        response = pipeline.ask(text)
        elapsed = round(time.time() - start, 1)
        answer = response.get("answer", "Sorry, I could not find an answer.")
        q_type = response.get("question_type", "search")
        sources = response.get("sources", [])
        entities = response.get("entities", {})

        # Pick the right card type
        if q_type == "aggregation":
            card = aggregation_card(text, answer, elapsed)
        elif q_type == "lookup":
            claim_id = entities.get("claim_id", "")
            card = lookup_card(text, answer, claim_id, elapsed)
        else:
            card = search_card(text, answer, sources[:5], elapsed)

        await send_card_reply(service_url, conversation_id, activity_id, card)

    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        card = error_card(text, str(e))
        await send_card_reply(service_url, conversation_id, activity_id, card)


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------

async def messages(req: web.Request) -> web.Response:
    """Main webhook endpoint. Teams sends every user message here."""
    try:
        body = await req.json()
        if body.get("type") == "message":
            asyncio.create_task(handle_message(body))
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Request error: {e}")
        return web.Response(status=200)


# ---------------------------------------------------------------------------
# Start server
# ---------------------------------------------------------------------------
app = web.Application()
app.router.add_post("/api/messages", messages)

if __name__ == "__main__":
    logger.info("Starting Teams bot server on port 8000...")
    logger.info(f"Messaging endpoint: POST /api/messages")
    logger.info(f"App ID    : {APP_ID}")
    logger.info(f"Tenant ID : {TENANT_ID}")
    logger.info(f"Secret set: {'Yes' if APP_SECRET else 'No'}")
    web.run_app(app, host="0.0.0.0", port=8000)
