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
