# =============================================================================
# bot/teams_bot.py
# Teams Bot — handles incoming messages from Microsoft Teams
# =============================================================================

import logging
from botbuilder.core import ActivityHandler, TurnContext, MessageFactory
from botbuilder.schema import ChannelAccount

logger = logging.getLogger("claims.bot")


class ClaimsBot(ActivityHandler):
    """
    Microsoft Teams bot that receives messages and routes them
    through the RAG pipeline to generate answers.
    """

    def __init__(self, pipeline):
        """
        Args:
            pipeline: Initialised RAGPipeline instance
        """
        super().__init__()
        self.pipeline = pipeline

    async def on_message_activity(self, turn_context: TurnContext):
        """
        Called every time a user sends a message to the bot in Teams.
        Strips the bot mention, passes question to RAG pipeline,
        and replies with the answer.
        """
        # Get the message text and strip bot mention (@ClaimsBot)
        question = turn_context.activity.text or ""
        question = question.strip()

        # Remove bot mention if present (e.g. "<at>Claims Assistant</at>")
        if "<at>" in question:
            import re
            question = re.sub(r'<at>.*?</at>', '', question).strip()

        if not question:
            await turn_context.send_activity(
                MessageFactory.text("Hi! Ask me anything about your claims data. 📋")
            )
            return

        # Handle help command
        if question.lower() in ["help", "@help", "hi", "hello"]:
            help_text = (
                "👋 **Claims Assistant** — ask me anything about your claims data!\n\n"
                "**Example questions:**\n"
                "• How many open claims are there?\n"
                "• What is the total claim value?\n"
                "• Give me total value by ClaimType\n"
                "• Tell me about claim CLM0000003\n"
                "• Show me high value medical claims\n"
                "• Which region has the most claims?\n\n"
                "Just type your question and I'll answer it!"
            )
            await turn_context.send_activity(MessageFactory.text(help_text))
            return

        # Show typing indicator
        await turn_context.send_activity(MessageFactory.text("🤔 Thinking..."))

        try:
            # Route through RAG pipeline
            response = self.pipeline.ask(question)
            answer   = response.get("answer", "Sorry, I could not find an answer.")
            q_type   = response.get("question_type", "")
            sources  = response.get("sources", [])

            # Build reply with metadata
            reply = answer

            # Add source claim IDs for search answers
            if sources and q_type == "search":
                source_list = ", ".join(sources[:5])
                reply += f"\n\n_Sources: {source_list}_"

            # Add response type indicator
            type_emoji = {"aggregation": "⚡", "lookup": "🔍", "search": "🤖"}.get(q_type, "")
            if type_emoji:
                reply += f"\n_{type_emoji} {q_type}_"

            await turn_context.send_activity(MessageFactory.text(reply))

        except Exception as e:
            logger.error(f"Bot error: {e}")
            await turn_context.send_activity(
                MessageFactory.text("⚠️ Something went wrong. Please try again.")
            )

    async def on_members_added_activity(
        self, members_added, turn_context: TurnContext
    ):
        """Greet new members when they join the conversation."""
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(
                    MessageFactory.text(
                        "👋 Hi! I'm the **Claims Assistant**.\n\n"
                        "Ask me anything about your claims data in plain English.\n"
                        "Type **help** to see example questions."
                    )
                )
