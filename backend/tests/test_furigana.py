from __future__ import annotations

import pytest

from app.services.furigana import (
    render_furigana,
    strip_all_furigana,
    strip_furigana_inside_bold,
    strip_malformed_furigana,
)

SIMPLE = "お<ruby>母<rt>かあ</rt></ruby>さんが<ruby>昼寝<rt>ひるね</rt></ruby>をしている。"
WITH_BOLD_TARGET = (
    "<ruby>富士山<rt>ふじさん</rt></ruby>に<ruby><b>登</b><rt>のぼ</rt></ruby>ってみたい。"
)
# Mirrors the real ADR-6 malformed seed row: the <rt> for a single-kanji base ("子") holds
# the rest of the sentence instead of a short kana reading.
MALFORMED = "<ruby>子<rt>どもたちはテレビをみていた。</rt></ruby>どもたちはテレビを見ていた。"


def test_render_always_returns_html_unchanged_when_well_formed() -> None:
    assert render_furigana(SIMPLE, "always") == SIMPLE


def test_render_never_strips_every_rt_payload() -> None:
    rendered = strip_all_furigana(SIMPLE)
    assert "<rt>" not in rendered
    assert "母" in rendered and "昼寝" in rendered
    assert render_furigana(SIMPLE, "never") == rendered


def test_render_by_level_strips_only_inside_bold() -> None:
    rendered = strip_furigana_inside_bold(WITH_BOLD_TARGET)
    assert "ふじさん" in rendered  # context reading kept
    assert "のぼ" not in rendered  # tested-target reading stripped
    assert render_furigana(WITH_BOLD_TARGET, "by_level") == rendered


def test_render_unknown_mode_raises() -> None:
    with pytest.raises(Exception, match="[Uu]nknown furigana mode|violates type hint"):
        render_furigana(SIMPLE, "bogus")  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", ["always", "never", "by_level"])
def test_malformed_rt_is_dropped_in_every_mode(mode: str) -> None:
    """A single-kanji <rt> holding an entire clause must never reach the page, regardless
    of furigana mode — see ARCHITECTURE.md ADR-6/ADR-6b."""
    rendered = render_furigana(MALFORMED, mode)  # type: ignore[arg-type]
    assert "どもたちはテレビをみていた。" not in rendered
    assert "子" in rendered  # base text stays visible


def test_strip_malformed_furigana_keeps_plausible_readings() -> None:
    # A 3-kanji base with a 4-kana reading is well within the plausible ratio and must survive.
    assert strip_malformed_furigana(WITH_BOLD_TARGET) == WITH_BOLD_TARGET


def test_strip_malformed_furigana_is_noop_on_plain_text() -> None:
    plain = "何もない普通の文。"
    assert strip_malformed_furigana(plain) == plain


def test_strip_malformed_furigana_handles_empty_string() -> None:
    assert strip_malformed_furigana("") == ""
