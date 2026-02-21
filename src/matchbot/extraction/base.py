from abc import ABC, abstractmethod

from matchbot.extraction.schemas import ExtractedPost


class ExtractionError(Exception):
    """Raised when LLM extraction fails or returns unparseable output."""


class LLMExtractor(ABC):
    @abstractmethod
    async def extract(
        self,
        title: str,
        body: str,
        platform: str,
        source_community: str,
    ) -> ExtractedPost: ...

    @abstractmethod
    def provider_name(self) -> str: ...

    async def aclose(self) -> None:
        """Optional async cleanup hook for provider clients."""
        return None
