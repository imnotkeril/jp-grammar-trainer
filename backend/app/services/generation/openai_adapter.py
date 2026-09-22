from __future__ import annotations

import json

from beartype import beartype
from openai import AsyncOpenAI

from app.config import settings
from app.services.generation.prompts import (
    GENERATION_JSON_SCHEMA,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from app.services.generation.provider import GenerationPrompt, RawGeneratedSentence


class OpenAIAdapter:
    """LLMProvider implementation backed by the OpenAI API.

    Uses structured outputs (response_format=json_schema) rather than free-text parsing,
    per ARCHITECTURE.md §7.2 — keeps both adapters returning an identical shape.
    """

    model_name: str = "gpt-4o-mini"

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or settings.openai_api_key
        if not key:
            raise RuntimeError("OPENAI_API_KEY is not configured but the OpenAI adapter was invoked.")
        self._client = AsyncOpenAI(api_key=key)

    @beartype
    async def generate_sentences(self, prompt: GenerationPrompt) -> list[RawGeneratedSentence]:
        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(prompt)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "generated_sentences",
                    "schema": GENERATION_JSON_SCHEMA,
                    "strict": True,
                },
            },
        )
        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("OpenAI returned an empty structured-output response.")
        payload = json.loads(content)
        return [RawGeneratedSentence(**item) for item in payload["sentences"]]
