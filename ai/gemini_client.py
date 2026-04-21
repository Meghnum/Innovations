import os
import time
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


def gemini_code_gen(prompt: str, timeout: int = 15) -> str:
    """
    Thin wrapper for Gemini 2.5 Flash.
    Used exclusively by the Pandas Agent for complex code generation.
    Includes exponential backoff for transient 503/429 errors.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable not set.")
        return "ERROR: GEMINI_API_KEY not found in environment variables."

    # Initialize client
    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        logger.error(f"Failed to initialize Gemini client: {e}")
        return f"ERROR: Gemini client init failed: {e}"

    max_attempts = 3
    base_delay = 2

    for attempt in range(max_attempts):
        try:
            # Call Gemini with strict deterministic temperature
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                ),
            )
            return response.text

        except Exception as e:
            logger.warning(f"Gemini API Error on attempt {attempt + 1}: {str(e)}")
            if attempt == max_attempts - 1:
                logger.error("Max retries reached. Gemini API execution failed.")
                return f"ERROR: Gemini API execution failed: {str(e)}"

            # Exponential backoff: 2s, 4s...
            sleep_time = base_delay * (2 ** attempt)
            logger.info(f"Retrying in {sleep_time} seconds...")
            time.sleep(sleep_time)
