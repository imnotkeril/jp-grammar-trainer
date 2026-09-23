from __future__ import annotations

from beartype import beartype
from anthropic import AsyncAnthropic

from app.config import settings
from app.services.generation.prompts import (
    GENERATION_JSON_SCHEMA,
    RELATION_CLASSIFICATION_JSON_SCHEMA,
    RELATION_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_relation_classification_prompt,
    build_user_prompt,
)
from app.services.generation.provider import (
    GenerationPrompt,
    RawGeneratedSentence,
    RelationCandidate,
    RelationClassification,
)

_TOOL_NAME = "return_generated_sentences"
_RELATION_TOOL_NAME = "return_relation_classifications"


class AnthropicAdapter:
    """LLMProvider implementation backed by the Anthropic API.

    Uses forced tool-use (tool_choice={"type": "tool", "name": ...}) to get the same
    structured JSON shape as the OpenAI adapter, per ARCHITECTURE.md §7.2.
    """

    model_name: str = "claude-3-5-haiku-latest"

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or settings.anthropic_api_key
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured but the Anthropic adapter was invoked.")
        self._client = AsyncAnthropic(api_key=key)

    @beartype
    async def generate_sentences(self, prompt: GenerationPrompt) -> list[RawGeneratedSentence]:
        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(prompt)}],
            tools=[
                {
                    "name": _TOOL_NAME,
                    "description": "Return the generated example sentences as structured JSON.",
                    "input_schema": GENERATION_JSON_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == _TOOL_NAME:
                tool_input = block.input
                assert isinstance(tool_input, dict)  # guaranteed by our own JSON schema
                sentences = tool_input.get("sentences", [])
                assert isinstance(sentences, list)
                return [RawGeneratedSentence(**item) for item in sentences]
        raise RuntimeError("Anthropic response did not contain the expected tool_use block.")

    @beartype
    async def classify_relations(
        self, candidates: list[RelationCandidate]
    ) -> list[RelationClassification]:
        """See ARCHITECTURE.md V2.2 step 2 — batched relation classification."""
        response = await self._client.messages.create(
            model=self.model_name,
            max_tokens=4096,
            system=RELATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_relation_classification_prompt(candidates)}],
            tools=[
                {
                    "name": _RELATION_TOOL_NAME,
                    "description": "Return the relation classifications as structured JSON.",
                    "input_schema": RELATION_CLASSIFICATION_JSON_SCHEMA,
                }
            ],
            tool_choice={"type": "tool", "name": _RELATION_TOOL_NAME},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == _RELATION_TOOL_NAME:
                tool_input = block.input
                assert isinstance(tool_input, dict)  # guaranteed by our own JSON schema
                classifications = tool_input.get("classifications", [])
                assert isinstance(classifications, list)
                return [RelationClassification(**item) for item in classifications]
        raise RuntimeError("Anthropic response did not contain the expected tool_use block.")
