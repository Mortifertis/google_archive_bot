"""Tests for Google Drive archive folder management."""

from unittest.mock import MagicMock

from app.google_drive import (ARCHIVE_APP_PROPERTIES, FOLDER_MIME_TYPE,
                              ensure_archive_folder)


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
