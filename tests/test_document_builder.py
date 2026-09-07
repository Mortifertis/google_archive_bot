"""Tests for building DOCX documents from Telegram posts."""

from datetime import datetime, timezone

from docx import Document

from app.document_builder import (
    MAX_TITLE_LENGTH,
    build_document_title,
    build_post_docx,
)
from app.telegram_parser import ForwardedPost


def _post(**changes: object) -> ForwardedPost:
    values = {
        "source_chat_id": -100123,
        "source_chat_title": "Some Channel",
        "source_chat_username": "somechannel",
        "source_message_id": 12345,
        "source_date": datetime(2026, 9, 7, 18, 40, tzinfo=timezone.utc),
        "source_url": "https://t.me/somechannel/12345",
        "text": "\n  Первая   содержательная строка  \nВторой абзац",
        "caption": None,
        "media_group_id": None,
        "photo_count": 0,
        "is_channel_post": True,
    }
    values.update(changes)
    return ForwardedPost(**values)


def test_title_contains_date_channel_and_first_meaningful_line() -> None:
    title = build_document_title(_post())

    assert title == (
        "2026-09-07 — Some Channel — Первая содержательная строка"
    )


def test_title_is_limited() -> None:
    title = build_document_title(_post(text="x" * 300))

    assert len(title) == MAX_TITLE_LENGTH
    assert title.endswith("…")


def test_docx_can_be_opened_and_contains_complete_unicode_text() -> None:
    post = _post(text="Первый абзац\n\nВторой абзац с Unicode: ёж 🦔")

    document = Document(build_post_docx(post))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]

    assert build_document_title(post) in paragraphs
    assert "Источник: Some Channel (@somechannel)" in paragraphs
    assert "Оригинал: https://t.me/somechannel/12345" in paragraphs
    assert "Первый абзац" in paragraphs
    assert "" in paragraphs
    assert "Второй абзац с Unicode: ёж 🦔" in paragraphs


def test_caption_is_used_when_text_is_missing() -> None:
    document = Document(build_post_docx(_post(text=None, caption="Подпись")))

    assert "Подпись" in [item.text for item in document.paragraphs]
