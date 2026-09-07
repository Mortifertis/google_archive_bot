"""Tests for building DOCX documents from Telegram posts."""

import base64
from datetime import datetime, timezone

from docx import Document

from app.document_builder import (MAX_TITLE_LENGTH, build_document_title,
                                  build_post_docx)
from app.telegram_media import DownloadedPhoto
from app.telegram_parser import ForwardedPost

PNG_DATA = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "/wcAAusB9Wl2nF0AAAAASUVORK5CYII="
)


def _photo(unique_id: str = "photo") -> DownloadedPhoto:
    return DownloadedPhoto(PNG_DATA, 1, 1, unique_id)


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


def test_single_photo_is_embedded() -> None:
    document = Document(build_post_docx(_post(), [_photo()]))

    assert len(document.inline_shapes) == 1
    assert "Изображения" in [item.text for item in document.paragraphs]


def test_three_photos_are_embedded_in_supplied_order() -> None:
    photos = [_photo("first"), _photo("second"), _photo("third")]

    document = Document(build_post_docx(_post(), photos))

    assert [photo.file_unique_id for photo in photos] == [
        "first",
        "second",
        "third",
    ]
    assert len(document.inline_shapes) == 3


def test_text_only_document_has_no_images_section() -> None:
    document = Document(build_post_docx(_post()))

    assert len(document.inline_shapes) == 0
    assert "Изображения" not in [item.text for item in document.paragraphs]


def test_caption_and_photo_are_both_preserved() -> None:
    caption = "Полная подпись\nсо второй строкой"
    document = Document(
        build_post_docx(
            _post(text=None, caption=caption, photo_count=1),
            [_photo()],
        )
    )

    paragraphs = [item.text for item in document.paragraphs]
    assert "Полная подпись" in paragraphs
    assert "со второй строкой" in paragraphs
    assert len(document.inline_shapes) == 1


def test_photo_without_caption_builds_without_placeholder_text() -> None:
    document = Document(
        build_post_docx(
            _post(text=None, caption=None, photo_count=1),
            [_photo()],
        )
    )

    paragraphs = [item.text for item in document.paragraphs]
    assert len(document.inline_shapes) == 1
    assert "Текст отсутствует" not in paragraphs
