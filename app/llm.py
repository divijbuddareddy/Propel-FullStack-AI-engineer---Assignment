"""Gemini LLM Integration with strict validation, retry, and safe fallback."""

import json
import os
import re
from typing import Optional, Tuple
from dotenv import load_dotenv

from app.prompts import SYSTEM_INSTRUCTION, USER_PROMPT_TEMPLATE, RETRY_CORRECTION_TEMPLATE
from app.schemas import CategoryEnum, SeverityEnum, LLMClassificationOutput

load_dotenv()

CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def extract_json_text(text: str) -> str:
    """Extracts raw JSON string from potentially markdown-fenced text."""
    text = text.strip()
    # Match ```json ... ``` or ``` ... ```
    fence_pattern = r"^```(?:json)?\s*([\s\S]*?)\s*```$"
    match = re.match(fence_pattern, text)
    if match:
        return match.group(1).strip()
    return text


def parse_and_validate_llm_json(raw_text: str) -> LLMClassificationOutput:
    """Parses and validates raw LLM output against LLMClassificationOutput schema."""
    clean_text = extract_json_text(raw_text)
    data = json.loads(clean_text)
    return LLMClassificationOutput.model_validate(data)


def create_safe_fallback() -> Tuple[LLMClassificationOutput, bool]:
    """Generates a deterministic safe fallback when model output is invalid or unavailable."""
    fallback = LLMClassificationOutput(
        category=CategoryEnum.UNKNOWN,
        severity=SeverityEnum.HIGH,
        reply_draft=(
            "Thank you for contacting Dhaba Support. We have received your request and "
            "our support team is reviewing it. We will get back to you shortly."
        ),
        needs_human=True,
        confidence=0.0
    )
    return fallback, True


class GeminiClient:
    """Client for invoking Gemini with schema validation, 1-retry mechanism, and safe fallback."""

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY", "")
        self.model_name = model_name or DEFAULT_MODEL
        self._client = None
        if self.api_key:
            self._init_client()

    def _init_client(self):
        """Initializes the official Google GenAI client."""
        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        except Exception:
            self._client = None

    def _call_gemini_raw(self, prompt: str) -> str:
        """Invokes Gemini with low temperature and JSON mode."""
        if not self._client:
            raise RuntimeError("Gemini client not configured or missing GOOGLE_API_KEY")

        from google.genai import types
        response = self._client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.1,
                response_mime_type="application/json",
            )
        )
        return response.text or ""

    def classify_ticket(self, subject: str, body: str) -> Tuple[LLMClassificationOutput, bool]:
        """Classifies a customer ticket with retry and safe fallback guarantees.
        
        Returns:
            Tuple of (LLMClassificationOutput, is_fallback_flag)
        """
        if not self.api_key or not self._client:
            # Degraded safe fallback when API key is not configured
            return create_safe_fallback()

        initial_prompt = USER_PROMPT_TEMPLATE.format(subject=subject, body=body)

        # 1. First Attempt
        raw_output = ""
        try:
            raw_output = self._call_gemini_raw(initial_prompt)
            output = parse_and_validate_llm_json(raw_output)
            # Apply low confidence policy
            if output.confidence < CONFIDENCE_THRESHOLD:
                output.needs_human = True
            return output, False
        except Exception as first_error:
            # 2. Retry Attempt (Exactly once on malformed/invalid response or transient failure)
            retry_prompt = RETRY_CORRECTION_TEMPLATE.format(
                error_message=str(first_error),
                previous_output=raw_output[:1000]
            )
            try:
                retry_output = self._call_gemini_raw(retry_prompt)
                output = parse_and_validate_llm_json(retry_output)
                if output.confidence < CONFIDENCE_THRESHOLD:
                    output.needs_human = True
                return output, False
            except Exception:
                # 3. Degraded Safe Fallback Path if retry also fails
                return create_safe_fallback()
