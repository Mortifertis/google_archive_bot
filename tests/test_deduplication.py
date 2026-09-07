"""Tests for the serialized archive deduplication workflow."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.config import GoogleConfig
from app.google_drive import DriveDocument
from app.handlers import _archive_with_deduplication
from app.telegram_parser import ForwardedPost


def _post(photo_count: int = 1) -> ForwardedPost:
    return ForwardedPost(
        source_chat_id=-1001,
        source_chat_title="Channel",
        source_chat_username="channel",
        source_message_id=42,
        source_date=None,
        source_url="https://t.me/channel/42",
        text="Caption",
        caption="Caption",
        media_group_id="album" if photo_count > 1 else None,
        photo_count=photo_count,
        is_channel_post=True,
    )


def _config() -> GoogleConfig:
    return GoogleConfig(
        credentials_path="credentials.json",
        token_path="token.json",
        archive_folder_name="Telegram Archive",
    )


@pytest.mark.asyncio
async def test_existing_photo_skips_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = DriveDocument("id", "Existing", "https://example.test/doc")
    monkeypatch.setattr(
        "app.handlers.find_existing_archived_post",
        lambda post, config: existing,
    )
    download = AsyncMock()

    document, duplicate, photos = await _archive_with_deduplication(
        _post(),
        _config(),
        asyncio.Lock(),
        download,
    )

    assert document == existing
    assert duplicate is True
    assert photos == ()
    download.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_album_skips_all_downloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = DriveDocument("id", "Album", "https://example.test/doc")
    monkeypatch.setattr(
        "app.handlers.find_existing_archived_post",
        lambda post, config: existing,
    )
    download = AsyncMock()

    await _archive_with_deduplication(
        _post(photo_count=3),
        _config(),
        asyncio.Lock(),
        download,
    )

    download.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_duplicate_creates_one_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: DriveDocument | None = None
    create_count = 0

    def find(
        post: ForwardedPost,
        config: GoogleConfig,
    ) -> DriveDocument | None:
        return created

    def archive(
        post: ForwardedPost,
        config: GoogleConfig,
        photos: object,
    ) -> DriveDocument:
        nonlocal create_count, created
        create_count += 1
        created = DriveDocument("id", "Created", "https://example.test/doc")
        return created

    monkeypatch.setattr("app.handlers.find_existing_archived_post", find)
    monkeypatch.setattr("app.handlers.archive_forwarded_post", archive)
    lock = asyncio.Lock()
    first_download = AsyncMock(return_value=())
    second_download = AsyncMock(return_value=())

    first, second = await asyncio.gather(
        _archive_with_deduplication(
            _post(), _config(), lock, first_download
        ),
        _archive_with_deduplication(
            _post(), _config(), lock, second_download
        ),
    )

    assert create_count == 1
    assert first[1] is False
    assert second[1] is True
    first_download.assert_awaited_once()
    second_download.assert_not_awaited()
