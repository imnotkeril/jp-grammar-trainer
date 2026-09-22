from __future__ import annotations

from beartype import beartype

from app.services.generation.provider import GenerationPrompt

PROMPT_VERSION = "v1"

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
            },
        }
    },
    "required": ["sentences"],
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
