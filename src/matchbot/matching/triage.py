"""LLM triage for ambiguous score-band matches."""

from __future__ import annotations

import json

from pydantic import BaseModel, field_validator

from matchbot.db.models import Post
from matchbot.extraction.base import ExtractionError, LLMExtractor

TRIAGE_SYSTEM_PROMPT = """\
You are helping a human moderator review potential matches between Burning Man camp seekers and camps with openings.

Given summaries of two posts (one seeker, one camp), assess whether an introduction would be useful.

Respond ONLY with JSON:
{
  "recommend": true | false,
  "confidence": float (0.0–1.0),
  "rationale": "brief explanation"
}
"""


class TriageDecision(BaseModel):
    recommend: bool
    confidence: float
    rationale: str = ""

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


def _summarize_post(post: Post, role: str) -> str:
    vibes = post.vibes_list()
    contribs = post.contribution_types_list()
    return (
        f"Role: {role}\n"
        f"Vibes: {', '.join(vibes) if vibes else 'not specified'}\n"
        f"Contributions: {', '.join(contribs) if contribs else 'not specified'}\n"
        f"Year: {post.year or 'not specified'}\n"
        f"Notes: {post.availability_notes or 'none'}\n"
        f"Camp name: {post.camp_name or 'not specified'}"
    )


async def llm_triage(
    seeker: Post,
    camp: Post,
    extractor: LLMExtractor,
) -> tuple[float, str]:
    """
    Ask LLM to evaluate a potential match.

    Returns (confidence, rationale_string).
    """
    seeker_summary = _summarize_post(seeker, "seeker")
    camp_summary = _summarize_post(camp, "camp")

    user_content = (
        f"SEEKER POST:\n{seeker_summary}\n\n"
        f"CAMP POST:\n{camp_summary}\n\n"
        "Would you recommend introducing these two? Respond with JSON only."
    )

    # We reuse the extractor's client but call it directly with a different prompt
    # For now, delegate to the extractor's underlying client via a helper
    try:
        result = await _call_triage(extractor, user_content)
        return result["confidence"], result.get("rationale", "")
    except Exception as exc:
        raise ExtractionError(f"LLM triage failed: {exc}") from exc


async def _call_triage(extractor: LLMExtractor, user_content: str) -> dict:
    """Route triage call to the correct provider."""
    provider = extractor.provider_name()

    if provider == "anthropic":
        from matchbot.extraction.anthropic_extractor import AnthropicExtractor

        assert isinstance(extractor, AnthropicExtractor)
        anthropic_response = await extractor._client.messages.create(
            model=extractor._model,
            max_tokens=512,
            system=TRIAGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        first_block = anthropic_response.content[0]
        if not hasattr(first_block, "text"):
            raise ExtractionError(f"Unexpected response block type: {type(first_block).__name__}")
        raw = first_block.text.strip()
    elif provider == "openai":
        from matchbot.extraction.openai_extractor import OpenAIExtractor, get_openai_refusal

        assert isinstance(extractor, OpenAIExtractor)
        openai_response = await extractor._client.responses.parse(
            model=extractor._model,
            max_output_tokens=512,
            instructions=TRIAGE_SYSTEM_PROMPT,
            input=user_content,
            text_format=TriageDecision,
        )
        refusal = get_openai_refusal(openai_response)
        if refusal:
            raise ExtractionError(f"OpenAI refused triage response: {refusal}")

        parsed = getattr(openai_response, "output_parsed", None)
        if parsed is None:
            raise ExtractionError("OpenAI returned no parsed triage response")

        if isinstance(parsed, TriageDecision):
            return parsed.model_dump()
        return TriageDecision.model_validate(parsed).model_dump()
    else:
        raise ExtractionError(f"Unknown provider for triage: {provider}")

    # Strip code fences
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    return json.loads(raw)
