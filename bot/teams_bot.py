# =============================================================================
# bot/teams_bot.py
# Teams Bot -- handles incoming messages from Microsoft Teams
# Routes questions through RAG pipeline and replies with Adaptive Cards
# =============================================================================

import logging
import re
import time

from botbuilder.core import ActivityHandler, TurnContext, MessageFactory
from botbuilder.schema import Activity

from bot.adaptive_cards import (
    aggregation_card,
    lookup_card,
    search_card,
    error_card,
    help_card,
    status_card,
)

logger = logging.getLogger("claims.bot")


class ClaimsBot(ActivityHandler):
    """
    Microsoft Teams bot that receives messages, routes them through the
    RAG pipeline, and replies with rich Adaptive Cards.
    """

    def __init__(self, pipeline):
        """
        Args:
            pipeline: Initialised RAGPipeline instance (must expose
                      .ask(), .rebuild(), and .loader attributes).
        """
        super().__init__()
        self.pipeline = pipeline

    # --------------------------------------------------------------------- #
    # Message handling
    # --------------------------------------------------------------------- #

    async def on_message_activity(self, turn_context: TurnContext):
        """Route the incoming message to the correct handler."""
        question = turn_context.activity.text or ""
        question = question.strip()

        # Strip bot @-mention if present
        if "<at>" in question:
            question = re.sub(r"<at>.*?</at>", "", question).strip()

        if not question:
            await self._send_card(turn_context, help_card())
            return

        lower = question.lower()

        # --- Built-in commands ------------------------------------------- #
        if lower in ("help", "hi", "hello"):
            await self._send_card(turn_context, help_card())
            return

        if lower == "status":
            await self._handle_status(turn_context)
            return

        if lower == "refresh":
            await self._handle_refresh(turn_context)
            return

        # --- Pipeline question ------------------------------------------- #
        await self._handle_question(turn_context, question)

    # --------------------------------------------------------------------- #
    # Command handlers
    # --------------------------------------------------------------------- #

    async def _handle_status(self, turn_context: TurnContext):
        """Send system status card."""
        try:
            loader = self.pipeline.loader
            loader_info = {
                "rows": getattr(loader, "row_count", "N/A"),
                "columns": getattr(loader, "col_count", "N/A"),
                "last_refresh": getattr(loader, "last_refresh", "N/A"),
                "source": getattr(loader, "source", "N/A"),
            }
            llm_ok = getattr(self.pipeline, "llm_ok", True)
            card = status_card(loader_info, llm_ok)
            await self._send_card(turn_context, card)
        except Exception as e:
            logger.error(f"Status error: {e}")
            card = error_card("status", str(e))
            await self._send_card(turn_context, card)

    async def _handle_refresh(self, turn_context: TurnContext):
        """Rebuild pipeline and confirm."""
        try:
            await turn_context.send_activity(
                MessageFactory.text("Refreshing data...")
            )
            self.pipeline.rebuild()
            await turn_context.send_activity(
                MessageFactory.text("Data refresh complete.")
            )
        except Exception as e:
            logger.error(f"Refresh error: {e}")
            card = error_card("refresh", str(e))
            await self._send_card(turn_context, card)

    async def _handle_question(self, turn_context: TurnContext, question: str):
        """Ask the pipeline and reply with the appropriate card."""
        try:
            start = time.time()
            response = self.pipeline.ask(question)
            elapsed = time.time() - start

            answer = response.get("answer", "Sorry, I could not find an answer.")
            q_type = response.get("question_type", "")
            sources = response.get("sources", [])
            claim_id = response.get("claim_id", None)

            if q_type == "aggregation":
                card = aggregation_card(question, answer, elapsed)
            elif q_type == "lookup":
                card = lookup_card(question, answer, claim_id or "N/A", elapsed)
            elif q_type == "search":
                card = search_card(question, answer, sources, elapsed)
            else:
                # Default to aggregation style for unknown types
                card = aggregation_card(question, answer, elapsed)

            await self._send_card(turn_context, card)

        except Exception as e:
            logger.error(f"Bot error: {e}")
            card = error_card(question, "Something went wrong. Please try again.")
            await self._send_card(turn_context, card)

    # --------------------------------------------------------------------- #
    # Welcome
    # --------------------------------------------------------------------- #

    async def on_members_added_activity(self, members_added, turn_context: TurnContext):
        """Greet new members with the help card."""
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await self._send_card(turn_context, help_card())

    # --------------------------------------------------------------------- #
    # Helpers
    # --------------------------------------------------------------------- #

    async def _send_card(self, turn_context: TurnContext, card_payload: dict):
        """Deserialise an Adaptive Card payload and send it."""
        activity = Activity.deserialize(card_payload)
        await turn_context.send_activity(activity)
