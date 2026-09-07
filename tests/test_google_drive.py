"""Tests for Google Drive archive folder and document management."""

import logging
from unittest.mock import MagicMock

import pytest

from app.config import GoogleConfig
from app.google_drive import (ARCHIVE_APP_PROPERTIES, FOLDER_MIME_TYPE,
                              GOOGLE_DOC_MIME_TYPE, ensure_archive_folder,
                              find_archived_document,
                              find_existing_archived_post)
from app.telegram_parser import ForwardedPost


def _drive_service(list_responses: list[dict[str, object]]) -> MagicMock:
    service = MagicMock()
    service.files.return_value.list.return_value.execute.side_effect = (
        list_responses
    )
    return service


def test_existing_archive_folder_is_reused() -> None:
    service = _drive_service(
        [
            {
                "files": [
                    {
                        "id": "existing-id",
                        "name": "Telegram Archive",
                        "createdTime": "2026-01-01T00:00:00Z",
                    }
                ]
            }
        ]
    )

    folder = ensure_archive_folder(service, "Telegram Archive")

    service.files.return_value.create.assert_not_called()
    assert folder.id == "existing-id"
    assert folder.web_url == (
        "https://drive.google.com/drive/folders/existing-id"
    )


def test_missing_archive_folder_is_created_with_metadata() -> None:
    service = _drive_service([{"files": []}])
    service.files.return_value.create.return_value.execute.return_value = {
        "id": "new-id",
        "name": "Telegram Archive",
    }

    folder = ensure_archive_folder(service, "Telegram Archive")

    service.files.return_value.create.assert_called_once_with(
        body={
            "name": "Telegram Archive",
            "mimeType": FOLDER_MIME_TYPE,
            "appProperties": ARCHIVE_APP_PROPERTIES,
        },
        fields="id, name",
    )
    assert folder.web_url == "https://drive.google.com/drive/folders/new-id"


def test_second_ensure_reuses_folder_created_by_first_call() -> None:
    service = _drive_service(
        [
            {"files": []},
            {
                "files": [
                    {
                        "id": "new-id",
                        "name": "Telegram Archive",
                        "createdTime": "2026-01-01T00:00:00Z",
                    }
                ]
            },
        ]
    )
    service.files.return_value.create.return_value.execute.return_value = {
        "id": "new-id",
        "name": "Telegram Archive",
    }

    first = ensure_archive_folder(service, "Telegram Archive")
    second = ensure_archive_folder(service, "Telegram Archive")

    service.files.return_value.create.assert_called_once()
    assert first == second


def test_oldest_duplicate_archive_folder_is_selected() -> None:
    service = _drive_service(
        [
            {
                "files": [
                    {
                        "id": "newer",
                        "name": "Telegram Archive",
                        "createdTime": "2026-02-01T00:00:00Z",
                    },
                    {
                        "id": "older",
                        "name": "Telegram Archive",
                        "createdTime": "2026-01-01T00:00:00Z",
                    },
                ]
            }
        ]
    )

    folder = ensure_archive_folder(service, "Telegram Archive")

    assert folder.id == "older"


def test_google_document_is_imported_with_metadata() -> None:
    from io import BytesIO

    from app.google_drive import (DOCX_MIME_TYPE, GOOGLE_DOC_MIME_TYPE,
                                  create_google_document)

    service = MagicMock()
    service.files.return_value.create.return_value.execute.return_value = {
        "id": "document-id",
        "name": "Document title",
    }

    document = create_google_document(
        service,
        "folder-id",
        "Document title",
        BytesIO(b"docx bytes"),
        {
            "application": "telegram_archive_bot",
            "purpose": "archived_post",
            "source_chat_id": "-1001",
            "source_message_id": "42",
        },
    )

    create_call = service.files.return_value.create
    create_call.assert_called_once()
    call = create_call.call_args.kwargs
    assert call["body"] == {
        "name": "Document title",
        "mimeType": GOOGLE_DOC_MIME_TYPE,
        "parents": ["folder-id"],
        "appProperties": {
            "application": "telegram_archive_bot",
            "purpose": "archived_post",
            "source_chat_id": "-1001",
            "source_message_id": "42",
        },
    }
    assert call["media_body"]._mimetype == DOCX_MIME_TYPE
    assert call["media_body"]._resumable is False
    assert call["fields"] == "id, name"
    assert document.web_url == (
        "https://docs.google.com/document/d/document-id/edit"
    )


def test_archived_document_is_found_by_telegram_source() -> None:
    service = _drive_service(
        [
            {
                "files": [
                    {
                        "id": "document-id",
                        "name": "Saved post",
                        "createdTime": "2026-01-01T00:00:00Z",
                    }
                ]
            }
        ]
    )

    document = find_archived_document(service, -1001, 42)

    assert document is not None
    assert document.name == "Saved post"
    assert document.web_url == (
        "https://docs.google.com/document/d/document-id/edit"
    )

    list_call = service.files.return_value.list.call_args.kwargs
    query = list_call["q"]
    assert "trashed = false" in query
    assert f"mimeType = '{GOOGLE_DOC_MIME_TYPE}'" in query
    assert "key='application'" in query
    assert "value='telegram_archive_bot'" in query
    assert "key='purpose'" in query
    assert "value='archived_post'" in query
    assert "key='source_chat_id'" in query
    assert "value='-1001'" in query
    assert "key='source_message_id'" in query
    assert "value='42'" in query
    assert "parents" not in query
    assert list_call["fields"] == (
        "nextPageToken, files(id, name, createdTime)"
    )


def test_missing_archived_document_returns_none() -> None:
    service = _drive_service([{"files": []}])

    assert find_archived_document(service, -1001, 42) is None
    service.files.return_value.create.assert_not_called()


def test_oldest_archived_document_is_selected_across_pages(
    caplog: object,
) -> None:
    service = _drive_service(
        [
            {
                "files": [
                    {
                        "id": "newer",
                        "name": "Newer",
                        "createdTime": "2026-02-01T00:00:00Z",
                    }
                ],
                "nextPageToken": "next-page",
            },
            {
                "files": [
                    {
                        "id": "older",
                        "name": "Older",
                        "createdTime": "2026-01-01T00:00:00Z",
                    }
                ]
            },
        ]
    )

    with caplog.at_level(logging.WARNING):
        document = find_archived_document(service, -1001, 42)

    assert document is not None
    assert document.id == "older"
    assert service.files.return_value.list.call_count == 2
    assert (
        service.files.return_value.list.call_args_list[1].kwargs["pageToken"]
        == "next-page"
    )
    service.files.return_value.create.assert_not_called()
    assert "Multiple archived documents found" in caplog.text


@pytest.mark.parametrize(
    ("source_chat_id", "source_message_id"),
    ((None, 42), (-1001, None)),
)
def test_missing_source_coordinate_skips_drive_lookup(
    source_chat_id: int | None,
    source_message_id: int | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials = MagicMock()
    monkeypatch.setattr(
        "app.google_drive.get_google_credentials",
        credentials,
    )
    post = ForwardedPost(
        source_chat_id=source_chat_id,
        source_chat_title=None,
        source_chat_username=None,
        source_message_id=source_message_id,
        source_date=None,
        source_url=None,
        text="Post",
        caption=None,
        media_group_id=None,
        photo_count=0,
        is_channel_post=True,
    )
    config = GoogleConfig("credentials.json", "token.json", "Archive")

    assert find_existing_archived_post(post, config) is None
    credentials.assert_not_called()
