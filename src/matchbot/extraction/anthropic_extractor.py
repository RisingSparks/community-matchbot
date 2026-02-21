"""Anthropic (Claude) LLM extractor."""

import json

import anthropic

from matchbot.extraction.base import ExtractionError, LLMExtractor
from matchbot.extraction.prompts import SYSTEM_PROMPT, build_user_prompt
from matchbot.extraction.schemas import ExtractedPost
from matchbot.settings import get_settings


class AnthropicExtractor(LLMExtractor):
    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        settings = get_settings()
        self._client = client or anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def provider_name(self) -> str:
        return "anthropic"

    async def extract(
        self,
        title: str,
        body: str,
        platform: str,
        source_community: str,
    ) -> ExtractedPost:
        user_prompt = build_user_prompt(title, body, platform, source_community)

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=None,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except anthropic.APIError as exc:
            raise ExtractionError(f"Anthropic API error: {exc}") from exc

        first_block = response.content[0]
        if not hasattr(first_block, "text"):
            raise ExtractionError(f"Unexpected response block type: {type(first_block).__name__}")
        raw = first_block.text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"Failed to parse LLM JSON response: {exc}\nRaw: {raw}") from exc

        try:
            return ExtractedPost(**data)
        except Exception as exc:
            raise ExtractionError(f"ExtractedPost validation failed: {exc}") from exc
