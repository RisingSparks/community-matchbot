"""Anthropic (Claude) LLM extractor."""

import inspect

import anthropic

from matchbot.extraction.base import ExtractionError, LLMExtractor
from matchbot.extraction.prompts import SYSTEM_PROMPT, build_user_prompt
from matchbot.extraction.schemas import ExtractedPost
from matchbot.settings import get_settings


def get_anthropic_refusal(response: object) -> str | None:
    """Extract refusal text from an Anthropic response, if present."""
    if getattr(response, "stop_reason", None) != "refusal":
        return None
    content = getattr(response, "content", None) or []
    for block in content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", None)
    return "Request refused by Anthropic safety system."


class AnthropicExtractor(LLMExtractor):
    def __init__(self, client: anthropic.AsyncAnthropic | None = None) -> None:
        settings = get_settings()
        self._client = client or anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def provider_name(self) -> str:
        return "anthropic"

    async def aclose(self) -> None:
        close = getattr(self._client, "close", None)
        if close is None:
            return
        result = close()
        if inspect.isawaitable(result):
            await result

    async def extract(
        self,
        title: str,
        body: str,
        platform: str,
        source_community: str,
    ) -> ExtractedPost:
        user_prompt = build_user_prompt(title, body, platform, source_community)

        try:
            response = await self._client.messages.parse(
                model=self._model,
                max_tokens=None,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                output_format=ExtractedPost,
            )
        except anthropic.APIError as exc:
            raise ExtractionError(f"Anthropic API error: {exc}") from exc

        refusal = get_anthropic_refusal(response)
        if refusal:
            raise ExtractionError(
                f"Anthropic refused extraction. Model: {self._model}. Refusal: {refusal}"
            )

        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise ExtractionError(
                f"Anthropic returned no parsed extraction. Model: {self._model}. "
                f"stop_reason={getattr(response, 'stop_reason', None)!r}"
            )
        if isinstance(parsed, ExtractedPost):
            return parsed
        return ExtractedPost.model_validate(parsed)
