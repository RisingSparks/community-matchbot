"""OpenAI LLM extractor."""

import openai

from matchbot.extraction.base import ExtractionError, LLMExtractor
from matchbot.extraction.prompts import SYSTEM_PROMPT, build_user_prompt
from matchbot.extraction.schemas import ExtractedPost
from matchbot.settings import get_settings


def get_openai_refusal(response: object) -> str | None:
    """Extract refusal text from a Responses API object, if present."""
    output = getattr(response, "output", None)
    if not output:
        return None
    for out in output:
        if getattr(out, "type", None) != "message":
            continue
        for item in getattr(out, "content", []):
            if getattr(item, "type", None) == "refusal":
                return getattr(item, "refusal", None)
    return None


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
            response = await self._client.responses.parse(
                model=self._model,
                max_output_tokens=None,
                instructions=SYSTEM_PROMPT,
                input=user_prompt,
                text_format=ExtractedPost,
                **extra,
            )
        except openai.APIError as exc:
            raise ExtractionError(f"OpenAI API error: {exc}") from exc

        refusal = get_openai_refusal(response)
        if refusal:
            raise ExtractionError(
                f"OpenAI refused extraction. Model: {self._model}. Refusal: {refusal}"
            )

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise ExtractionError(
                f"OpenAI returned no parsed extraction. Model: {self._model}. "
                f"status={getattr(response, 'status', None)!r} "
                f"incomplete_details={getattr(response, 'incomplete_details', None)!r}"
            )
        if isinstance(parsed, ExtractedPost):
            return parsed
        return ExtractedPost.model_validate(parsed)
