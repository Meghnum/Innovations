import os
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


def gemini_code_gen(prompt: str, timeout: int = 15) -> str:
    """
    Thin wrapper for Gemini 2.5 Flash.
    Used exclusively by the Pandas Agent for complex code generation.
    Returns the model's raw text, or an "ERROR: ..." sentinel that matches
    the contract pandas_agent already understands.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable not set.")
        return "ERROR: GEMINI_API_KEY not found in environment variables."

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
            ),
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini API Error: {str(e)}")
        return f"ERROR: Gemini API execution failed: {str(e)}"
