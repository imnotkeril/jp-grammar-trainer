from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from beartype import beartype


@dataclass(frozen=True, slots=True)
class GenerationPrompt:
    """Everything an adapter needs to ask the model for new example sentences.

    See ARCHITECTURE.md §7.3 for the prompt shape this backs.
    """

    pattern_text: str
    target_construction: str
    formation_rules: list[str]
    existing_example_clean: str
    existing_sentences: list[str]
    batch_size: int


@dataclass(frozen=True, slots=True)
class RawGeneratedSentence:
    """One structured-output item, before validation (ARCHITECTURE.md §7.4)."""

    sentence_full_html: str
    sentence_with_blank_html: str
    correct_answer_text: str
    explanation_ru: str


class LLMProvider(Protocol):
    """Provider-agnostic contract. Implemented by openai_adapter.py / anthropic_adapter.py.

    Both adapters return the same structured shape so app/services/generation/trigger.py
    and validate.py never need to know which provider answered.
    """

    model_name: str

    async def generate_sentences(self, prompt: GenerationPrompt) -> list[RawGeneratedSentence]: ...


@beartype
def build_prompt(
    pattern_text: str,
    target_construction: str,
    formation_rules: list[str],
    existing_example_clean: str,
    existing_sentences: list[str],
    batch_size: int,
) -> GenerationPrompt:
    return GenerationPrompt(
        pattern_text=pattern_text,
        target_construction=target_construction,
        formation_rules=formation_rules,
        existing_example_clean=existing_example_clean,
        existing_sentences=existing_sentences[:20],
        batch_size=batch_size,
    )
