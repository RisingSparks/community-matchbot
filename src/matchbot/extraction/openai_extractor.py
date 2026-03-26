"""OpenAI LLM extractor."""

import asyncio
import inspect
import logging

import openai

from matchbot.extraction.base import ExtractionError, LLMExtractor
from matchbot.extraction.prompts import SYSTEM_PROMPT, build_user_prompt
from matchbot.extraction.schemas import ExtractedPost
from matchbot.settings import get_settings

logger = logging.getLogger(__name__)

_OPENAI_RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
_OPENAI_MAX_RETRIES = 4
_OPENAI_INITIAL_RETRY_DELAY_SECONDS = 2.0
_OPENAI_MAX_RETRY_DELAY_SECONDS = 30.0


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

        extra: dict = {}
        if self._service_tier is not None:
            extra["service_tier"] = self._service_tier

        try:
            response = await self._responses_parse_with_retry(
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

    async def _responses_parse_with_retry(self, **kwargs: object) -> object:
        attempt = 0
        while True:
            try:
                return await self._client.responses.parse(**kwargs)
            except openai.APIError as exc:
                if not _is_retryable_openai_error(exc) or attempt >= _OPENAI_MAX_RETRIES:
                    raise

                delay = _retry_delay_seconds(exc, attempt)
                attempt += 1
                logger.warning(
                    "OpenAI request failed with %s; retrying in %.1fs (attempt %s/%s).",
                    type(exc).__name__,
                    delay,
                    attempt,
                    _OPENAI_MAX_RETRIES,
                )
                await asyncio.sleep(delay)


def _is_retryable_openai_error(exc: openai.APIError) -> bool:
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError)):
        return True
    status_code = getattr(exc, "status_code", None)
    return isinstance(status_code, int) and status_code in _OPENAI_RETRYABLE_STATUS_CODES


def _retry_delay_seconds(exc: openai.APIError, attempt: int) -> float:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    retry_after = getattr(headers, "get", lambda _key: None)("Retry-After")
    if isinstance(retry_after, (str, int, float)) and retry_after != "":
        try:
            parsed = float(retry_after)
            if parsed > 0:
                return min(parsed, _OPENAI_MAX_RETRY_DELAY_SECONDS)
        except ValueError:
            pass
    return min(
        _OPENAI_INITIAL_RETRY_DELAY_SECONDS * (2**attempt),
        _OPENAI_MAX_RETRY_DELAY_SECONDS,
    )
