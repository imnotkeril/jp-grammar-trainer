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


@dataclass(frozen=True, slots=True)
class RelationCandidate:
    """One heuristically-scored candidate pair, ready to hand to the LLM classifier.

    See ARCHITECTURE.md V2 slice ("V2.2 Relation population strategy") — produced by
    app/scripts/generate_relations.py's heuristic step, consumed by classify_relations.
    """

    grammar_a_id: str
    grammar_a_text: str  # target_construction + short pattern_text summary
    grammar_a_meaning: str
    grammar_b_id: str
    grammar_b_text: str
    grammar_b_meaning: str


@dataclass(frozen=True, slots=True)
class RelationClassification:
    """One classified pair. `relation_type=None` means "no meaningful relation" — the
    caller discards it (no row written). See ARCHITECTURE.md V2.2 step 2/3.
    """

    grammar_a_id: str
    grammar_b_id: str
    relation_type: str | None  # one of the 7 grammar_relation_type enum values, or None
    direction: str | None  # "a_to_b" | "b_to_a", only meaningful for prerequisite/advanced_version
    strength: float  # 0..1 confidence
    note: str  # 1-sentence justification, stored verbatim in grammar_relation.note


class LLMProvider(Protocol):
    """Provider-agnostic contract. Implemented by openai_adapter.py / anthropic_adapter.py.

    Both adapters return the same structured shape so app/services/generation/trigger.py
    and validate.py never need to know which provider answered.
    """

    model_name: str

    async def generate_sentences(self, prompt: GenerationPrompt) -> list[RawGeneratedSentence]: ...

    async def classify_relations(
        self, candidates: list[RelationCandidate]
    ) -> list[RelationClassification]: ...


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
