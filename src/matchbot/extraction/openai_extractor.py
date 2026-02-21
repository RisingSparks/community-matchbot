"""OpenAI LLM extractor."""

import json

import openai

from matchbot.extraction.base import ExtractionError, LLMExtractor
from matchbot.extraction.prompts import SYSTEM_PROMPT, build_user_prompt
from matchbot.extraction.schemas import ExtractedPost
from matchbot.settings import get_settings


class OpenAIExtractor(LLMExtractor):
    def __init__(self, client: openai.AsyncOpenAI | None = None) -> None:
        settings = get_settings()
        self._client = client or openai.AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
        self._service_tier = settings.openai_service_tier

    def provider_name(self) -> str:
        return "openai"

    async def extract(
        self,
        title: str,
        body: str,
        platform: str,
        source_community: str,
    ) -> ExtractedPost:
        user_prompt = build_user_prompt(title, body, platform, source_community)

        extra: dict = {}
        if self._service_tier is not None:
            extra["service_tier"] = self._service_tier

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                max_completion_tokens=1024,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                **extra,
            )
        except openai.APIError as exc:
            raise ExtractionError(f"OpenAI API error: {exc}") from exc

        raw = response.choices[0].message.content or ""
        if not raw:
             # Check if there is reasoning_content or something else
             msg = response.choices[0].message
             debug_info = f"content={msg.content!r}"
             if hasattr(msg, "reasoning_content") and msg.reasoning_content:
                 debug_info += f" reasoning_content={msg.reasoning_content!r}"
             raise ExtractionError(f"OpenAI returned empty content. Model: {self._model}. {debug_info}")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"Failed to parse OpenAI JSON response: {exc}\nRaw: {raw}") from exc

        try:
            return ExtractedPost(**data)
        except Exception as exc:
            raise ExtractionError(f"ExtractedPost validation failed: {exc}") from exc
