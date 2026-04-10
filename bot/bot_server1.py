# =============================================================================
# bot/bot_server.py - Simplified Teams Bot using direct HTTP calls
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("claims.bot_server")

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

_token_cache = {"token": None, "expires_at": 0}

async def get_access_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]
    url  = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {"grant_type": "client_credentials", "client_id": APP_ID, "client_secret": APP_SECRET, "scope": "https://api.botframework.com/.default"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as resp:
            result = await resp.json()
            if "access_token" not in result:
                logger.error(f"Token error: {result}")
                raise PermissionError(f"Failed to get token: {result}")
            _token_cache["token"]      = result["access_token"]
            _token_cache["expires_at"] = time.time() + result.get("expires_in", 3600)
            logger.info("Access token obtained ✓")
            return _token_cache["token"]

async def send_reply(service_url, conversation_id, activity_id, text):
    token   = await get_access_token()
    url     = f"{service_url}v3/conversations/{conversation_id}/activities/{activity_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"type": "message", "text": text, "textFormat": "markdown"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status not in (200, 201):
                body = await resp.text()
                logger.error(f"Reply failed {resp.status}: {body}")
            else:
                logger.info("Reply sent successfully ✓")

async def handle_message(activity):
    text            = re.sub(r'<at>.*?</at>', '', activity.get("text", "")).strip()
    service_url     = activity.get("serviceUrl", "")
    conversation_id = activity.get("conversation", {}).get("id", "")
    activity_id     = activity.get("id", "")
    logger.info(f"Message received: '{text}'")
    if not text or text.lower() in ["hi", "hello", "help"]:
        reply = "👋 **Claims Assistant**\n\n**Examples:**\n• How many open claims are there?\n• What is the total claim value?\n• Give me total value by ClaimType\n• Tell me about claim CLM0000003\n• Show me high value medical claims"
    else:
        try:
            response = pipeline.ask(text)
            reply    = response.get("answer", "Sorry, I could not find an answer.")
            sources  = response.get("sources", [])
            # Only show sources if user asked "how do you know" or "show sources"
            text_lower = text.lower()
            if sources and any(kw in text_lower for kw in ["source", "how do you know", "evidence"]):
                reply += f"\n\n_Sources: {', '.join(sources[:5])}_"
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            reply = "⚠️ Something went wrong. Please try again."
    await send_reply(service_url, conversation_id, activity_id, reply)

async def messages(req):
    try:
        body = await req.json()
        if body.get("type") == "message":
            asyncio.create_task(handle_message(body))
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Request error: {e}")
        return web.Response(status=200)

app = web.Application()
app.router.add_post("/api/messages", messages)

if __name__ == "__main__":
    logger.info("Starting Teams bot server on port 8000...")
    logger.info(f"App ID: {APP_ID[:8]}..." if APP_ID else "⚠️  No App ID set in config")
    logger.info(f"App ID    : {APP_ID}")
    logger.info(f"Tenant ID : {TENANT_ID}")
    web.run_app(app, host="0.0.0.0", port=8000)