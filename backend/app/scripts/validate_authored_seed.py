"""Offline validator for authored grammar seed files (`data/seed/n*_grammar_authored.json`).

Run with:
    uv run python -m app.scripts.validate_authored_seed [path ...]
        # defaults to every data/seed/n?_grammar_authored.json

Needs no database. Exists so new levels (N5/N1 scaffolding, roadmap item 3) can be authored and
checked before they ever reach `seed_import_authored`, which only *flags* problems after the fact.
Format reference: `data/seed/README.md`. Exit code 1 when any file has an error (warnings do not fail).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from beartype import beartype

from app.scripts.seed_import import check_rt_payloads_are_kana, strip_tags

VALID_LEVELS = frozenset({"N5", "N4", "N3", "N2", "N1"})
REQUIRED_ITEM_FIELDS = (
    "key",
    "expression_html",
    "reading",
    "meaning_ru",
    "pattern_text",
    "target_construction",
)
_KEY_RE = re.compile(r"^n[1-5]_[a-z0-9_]+$")
_BOLD_RE = re.compile(r"<b>(.*?)</b>", re.DOTALL)
_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """`errors` block an import-ready file; `warnings` mirror what `seed_import_authored` only
    flags as anomalies (target/<b> mismatches exist in the shipped N2 data on purpose, e.g. a
    discontinuous construction like やら…やら)."""

    errors: list[str]
    warnings: list[str]


@beartype
def validate_payload(payload: object, filename: str = "<memory>") -> ValidationResult:
    """Human-readable problems for one parsed authored-seed file."""
    if not isinstance(payload, dict):
        return ValidationResult([f"{filename}: top level must be an object with 'level' and 'items'"], [])

    errors: list[str] = []
    warnings: list[str] = []
    level = payload.get("level")
    if level not in VALID_LEVELS:
        errors.append(f"{filename}: 'level' must be one of {sorted(VALID_LEVELS)}, got {level!r}")
    items = payload.get("items")
    if not isinstance(items, list):
        return ValidationResult([*errors, f"{filename}: 'items' must be a list"], warnings)

    seen_keys: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{filename}[{index}]: item must be an object")
            continue
        key = str(item.get("key", f"#{index}"))
        where = f"{filename}[{key}]"

        for field in REQUIRED_ITEM_FIELDS:
            if not isinstance(item.get(field), str) or not str(item.get(field)).strip():
                errors.append(f"{where}: missing or empty '{field}'")
        if "key" in item and isinstance(item["key"], str):
            if not _KEY_RE.match(item["key"]):
                errors.append(f"{where}: key must look like 'n5_001_name' (lowercase, level prefix)")
            elif isinstance(level, str) and not item["key"].startswith(level.lower() + "_"):
                errors.append(f"{where}: key prefix does not match file level {level}")
            if item["key"] in seen_keys:
                errors.append(f"{where}: duplicate key")
            seen_keys.add(item["key"])

        html = item.get("expression_html")
        target = item.get("target_construction")
        if isinstance(html, str):
            bold = _BOLD_RE.search(html)
            if bold is None:
                errors.append(f"{where}: expression_html has no <b>target</b> span")
            elif isinstance(target, str) and target and strip_tags(bold.group(1)).strip() != target:
                warnings.append(f"{where}: target_construction does not equal the <b> span text")
            if isinstance(target, str) and target and target not in strip_tags(html):
                warnings.append(f"{where}: target_construction does not appear in the sentence")
            if check_rt_payloads_are_kana(html):
                errors.append(f"{where}: malformed <rt> furigana payload")

        meaning = item.get("meaning_ru")
        if isinstance(meaning, str) and meaning.strip() and not _CYRILLIC_RE.search(meaning):
            errors.append(f"{where}: meaning_ru should be Russian")

        rules = item.get("formation_rules", [])
        if not isinstance(rules, list) or not all(
            isinstance(r, dict) and {"pos", "form_label", "example_html"} <= r.keys() for r in rules
        ):
            errors.append(f"{where}: formation_rules must be a list of {{pos, form_label, example_html}}")
        tags = item.get("tags", [])
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            errors.append(f"{where}: tags must be a list of strings")

    return ValidationResult(errors, warnings)


@beartype
def default_paths() -> list[Path]:
    seed_dir = Path(__file__).resolve().parents[3] / "data" / "seed"
    return sorted(seed_dir.glob("n?_grammar_authored.json"))


@beartype
def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]] or default_paths()
    failed = False
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        result = validate_payload(payload, path.name)
        count = len(payload.get("items", [])) if isinstance(payload, dict) else 0
        print(f"{path.name}: {count} items, {len(result.errors)} errors, {len(result.warnings)} warnings")
        for message in result.errors:
            print(f"  ERROR {message}")
        failed = failed or bool(result.errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
