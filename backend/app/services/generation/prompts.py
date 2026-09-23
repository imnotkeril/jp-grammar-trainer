from __future__ import annotations

from beartype import beartype

from app.services.generation.provider import GenerationPrompt, RelationCandidate

PROMPT_VERSION = "v1"
RELATION_PROMPT_VERSION = "v1"

RELATION_SYSTEM_PROMPT = (
    "You are a Japanese grammar taxonomy expert helping build a study graph for a "
    "Russian-speaking N3 learner. You always respond with the requested structured JSON "
    "and nothing else."
)

_RELATION_TYPES = (
    "similar_meaning",
    "similar_form",
    "commonly_confused",
    "opposite",
    "prerequisite",
    "advanced_version",
    "related",
)

# JSON schema shared by both adapters for the relation-classification pass. See
# ARCHITECTURE.md V2.2 step 2.
RELATION_CLASSIFICATION_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "grammar_a_id": {"type": "string"},
                    "grammar_b_id": {"type": "string"},
                    "relation_type": {
                        "type": ["string", "null"],
                        "enum": [*_RELATION_TYPES, None],
                    },
                    "direction": {"type": ["string", "null"], "enum": ["a_to_b", "b_to_a", None]},
                    "strength": {"type": "number"},
                    "note": {"type": "string"},
                },
                "required": [
                    "grammar_a_id",
                    "grammar_b_id",
                    "relation_type",
                    "direction",
                    "strength",
                    "note",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["classifications"],
    "additionalProperties": False,
}


@beartype
def build_relation_classification_prompt(candidates: list[RelationCandidate]) -> str:
    """Render the batched relation-classification prompt. See ARCHITECTURE.md V2.2 step 2.

    Batched ~40 pairs/call per the architect's design (app/scripts/generate_relations.py
    enforces the batch size; this function just renders whatever list it's given).
    """
    relation_types_bullets = "\n".join(f"- {rt}" for rt in _RELATION_TYPES)
    pairs = "\n\n".join(
        f"Pair (a_id={c.grammar_a_id}, b_id={c.grammar_b_id}):\n"
        f"  A: {c.grammar_a_text} — meaning (ru): {c.grammar_a_meaning}\n"
        f"  B: {c.grammar_b_text} — meaning (ru): {c.grammar_b_meaning}"
        for c in candidates
    )
    return f"""For each pair of Japanese N3 grammar constructions below, decide whether they have
one of these relation types (or none):
{relation_types_bullets}

- similar_meaning / similar_form / commonly_confused / opposite / related are SYMMETRIC —
  it doesn't matter which of A/B you call "a" or "b".
- prerequisite and advanced_version are DIRECTIONAL. If you pick one of these, also set
  "direction" to "a_to_b" (meaning: for prerequisite, A must be learned before B; for
  advanced_version, B is the more advanced form of A) or "b_to_a" (the reverse). For all
  other relation_type values (including null), set "direction" to null.
- If the pair has no meaningful pedagogical relation, set relation_type to null, direction
  to null, strength to 0.0, and note to a brief reason.
- strength is your confidence 0.0-1.0 that the relation_type (if any) is correct.
- note is a single sentence (can be in Russian or English) justifying the classification,
  suitable to show the learner as a tooltip.

Return exactly one classification object per pair, echoing back the same grammar_a_id/
grammar_b_id you were given.

{pairs}"""

SYSTEM_PROMPT = (
    "You are a Japanese N3 grammar exercise writer for a Russian-speaking learner. "
    "You always respond with the requested structured JSON and nothing else."
)

# JSON schema shared by both adapters (OpenAI response_format / Anthropic tool-use input
# schema). See ARCHITECTURE.md §7.2-7.3.
GENERATION_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "sentence_full_html": {"type": "string"},
                    "sentence_with_blank_html": {"type": "string"},
                    "correct_answer_text": {"type": "string"},
                    "explanation_ru": {"type": "string"},
                },
                "required": [
                    "sentence_full_html",
                    "sentence_with_blank_html",
                    "correct_answer_text",
                    "explanation_ru",
                ],
                # OpenAI structured-output "strict" mode requires additionalProperties:false
                # on every object in the schema (see openai_adapter.py); Anthropic's tool-use
                # schema tolerates the extra key harmlessly, so it's safe to set for both.
                "additionalProperties": False,
            },
        }
    },
    "required": ["sentences"],
    "additionalProperties": False,
}


@beartype
def build_user_prompt(prompt: GenerationPrompt) -> str:
    """Render the shared prompt template. See ARCHITECTURE.md §7.3."""
    formation_bullets = "\n".join(f"- {rule}" for rule in prompt.formation_rules) or "- (none provided)"
    existing = "\n".join(f"- {s}" for s in prompt.existing_sentences) or "- (none yet)"

    return f"""Grammar point: {prompt.pattern_text}
Target construction: {prompt.target_construction}
Formation rules:
{formation_bullets}
Existing example (for style/level calibration, do not repeat): {prompt.existing_example_clean}
Already-generated sentences for this grammar point (avoid near-duplicates):
{existing}

Generate {prompt.batch_size} NEW natural N3-level Japanese sentences that each correctly use
"{prompt.target_construction}". For each sentence return:
- sentence_full_html: the full sentence with <ruby><rt> furigana on kanji compounds
  (same markup convention as the example), and the target construction wrapped in <b>...</b>
- sentence_with_blank_html: same sentence with the target construction replaced by "___"
- correct_answer_text: the plain text that fills the blank
- explanation_ru (2-3 sentences, Russian): why this construction fits here, contrasted
  with a commonly confused alternative construction if relevant.
Vary sentence topic/register. Do not reuse the existing example's scenario."""
