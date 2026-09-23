from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.vocabulary import UserVocabulary, Vocabulary, VocabularyEntryType
from app.services.vocabulary import extract_ruby_bases, known_surface_forms, record_exposures


def make_vocab(
    db: Session,
    *,
    surface_form: str,
    entry_type: VocabularyEntryType = VocabularyEntryType.WORD,
    reading: str = "よみ",
    meaning_ru: str = "значение",
) -> Vocabulary:
    vocab = Vocabulary(
        surface_form=surface_form,
        entry_type=entry_type,
        reading=reading,
        meaning_ru=meaning_ru,
    )
    db.add(vocab)
    db.flush()
    return vocab


def test_extract_ruby_bases_returns_stripped_base_text() -> None:
    html = "お<ruby>母<rt>かあ</rt></ruby>さんが<ruby>昼寝<rt>ひるね</rt></ruby>をしている。"
    assert extract_ruby_bases(html) == ["母", "昼寝"]


def test_extract_ruby_bases_strips_inner_tags_like_bold() -> None:
    html = "<ruby><b>登</b><rt>のぼ</rt></ruby>ってみたい。"
    assert extract_ruby_bases(html) == ["登"]


def test_extract_ruby_bases_empty_when_no_ruby() -> None:
    assert extract_ruby_bases("何もない普通の文。") == []


def test_record_exposures_creates_row_on_first_correct_exposure(db_session: Session) -> None:
    vocab = make_vocab(db_session, surface_form="母")
    db_session.commit()
    now = datetime.now(timezone.utc)

    record_exposures(db_session, "<ruby>母<rt>かあ</rt></ruby>さん", is_correct=True, now=now)
    db_session.commit()

    uv = db_session.get(UserVocabulary, vocab.id)
    assert uv is not None
    assert uv.correct_exposures == 1
    assert uv.incorrect_exposures == 0
    assert uv.correct_streak == 1
    assert uv.known_since is None  # below threshold (default 5)
    assert uv.last_exposed_at == now


def test_record_exposures_sets_known_since_at_threshold(db_session: Session) -> None:
    vocab = make_vocab(db_session, surface_form="母")
    db_session.commit()
    now = datetime.now(timezone.utc)

    for i in range(5):
        record_exposures(
            db_session, "<ruby>母<rt>かあ</rt></ruby>さん", is_correct=True, now=now + timedelta(minutes=i)
        )
    db_session.commit()

    uv = db_session.get(UserVocabulary, vocab.id)
    assert uv is not None
    assert uv.correct_streak == 5
    assert uv.known_since is not None


def test_record_exposures_incorrect_resets_streak_and_clears_known_since(db_session: Session) -> None:
    vocab = make_vocab(db_session, surface_form="母")
    db_session.commit()
    now = datetime.now(timezone.utc)

    for i in range(5):
        record_exposures(
            db_session, "<ruby>母<rt>かあ</rt></ruby>さん", is_correct=True, now=now + timedelta(minutes=i)
        )
    db_session.commit()
    uv = db_session.get(UserVocabulary, vocab.id)
    assert uv is not None
    assert uv.known_since is not None

    record_exposures(
        db_session, "<ruby>母<rt>かあ</rt></ruby>さん", is_correct=False, now=now + timedelta(minutes=6)
    )
    db_session.commit()
    db_session.refresh(uv)
    assert uv.correct_streak == 0
    assert uv.known_since is None  # relapse, ADR-16
    assert uv.incorrect_exposures == 1


def test_record_exposures_noop_when_sentence_has_no_ruby(db_session: Session) -> None:
    make_vocab(db_session, surface_form="母")
    db_session.commit()
    now = datetime.now(timezone.utc)

    record_exposures(db_session, "何もない普通の文。", is_correct=True, now=now)
    db_session.commit()

    assert db_session.query(UserVocabulary).count() == 0


def test_record_exposures_ignores_words_not_in_vocabulary(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    record_exposures(db_session, "<ruby>未知<rt>みち</rt></ruby>の言葉。", is_correct=True, now=now)
    db_session.commit()
    assert db_session.query(UserVocabulary).count() == 0


def test_known_surface_forms_returns_only_known_words(db_session: Session) -> None:
    known_vocab = make_vocab(db_session, surface_form="母")
    unknown_vocab = make_vocab(db_session, surface_form="父", entry_type=VocabularyEntryType.WORD)
    db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add(UserVocabulary(vocabulary_id=known_vocab.id, correct_streak=5, known_since=now))
    db_session.add(UserVocabulary(vocabulary_id=unknown_vocab.id, correct_streak=1, known_since=None))
    db_session.commit()

    assert known_surface_forms(db_session) == frozenset({"母"})
