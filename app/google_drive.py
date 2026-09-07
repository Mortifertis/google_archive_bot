"""Google OAuth and Drive helpers for the archive folder setup."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

GOOGLE_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
ARCHIVE_APP_PROPERTIES = {
    "application": "telegram_archive_bot",
    "purpose": "archive_root",
}

logger = logging.getLogger(__name__)


class GoogleAuthError(RuntimeError):
    """An actionable error raised during local Google authorization."""


@dataclass(frozen=True, slots=True)
class DriveFolder:
    """The application-owned archive folder."""

    id: str
    name: str
    web_url: str


def _save_credentials(credentials: Credentials, token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")


def get_google_credentials(
    credentials_path: str,
    token_path: str,
) -> Credentials:
    """Load, refresh, or interactively obtain Google user credentials."""
    client_file = Path(credentials_path).expanduser()
    token_file = Path(token_path).expanduser()
    credentials: Credentials | None = None

    if token_file.is_file():
        try:
            credentials = Credentials.from_authorized_user_file(
                str(token_file),
                GOOGLE_DRIVE_SCOPES,
            )
        except (OSError, ValueError) as error:
            logger.warning("Google OAuth token could not be loaded: %s", error)
        else:
            logger.info("Google OAuth token loaded")

    if credentials and credentials.valid:
        return credentials

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except RefreshError:
            logger.warning(
                "Google OAuth token refresh failed; authorization is required"
            )
        else:
            _save_credentials(credentials, token_file)
            logger.info("Google OAuth token refreshed")
            return credentials

    if not client_file.is_file():
        raise GoogleAuthError(
            f"Google OAuth credentials file not found: {client_file}\n"
            "Create a Desktop OAuth client in Google Cloud Console and save "
            "the downloaded JSON as google_credentials.json."
        )

    logger.info("Google OAuth flow started")
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_file),
            GOOGLE_DRIVE_SCOPES,
        )
        credentials = flow.run_local_server(port=0)
    except (OSError, ValueError) as error:
        raise GoogleAuthError(
            "Google OAuth authorization could not be started. Check that the "
            "credentials file is a valid Desktop app client JSON."
        ) from error

    _save_credentials(credentials, token_file)
    return credentials


def build_drive_service(credentials: Credentials) -> Any:
    """Build a Google Drive API v3 service."""
    service = build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )
    logger.info("Google Drive service initialized")
    return service


def _to_drive_folder(folder: dict[str, str]) -> DriveFolder:
    folder_id = folder["id"]
    return DriveFolder(
        id=folder_id,
        name=folder["name"],
        web_url=f"https://drive.google.com/drive/folders/{folder_id}",
    )


def ensure_archive_folder(
    drive_service: Any,
    folder_name: str,
) -> DriveFolder:
    """Return the oldest application archive folder, creating it if absent."""
    query = (
        f"mimeType = '{FOLDER_MIME_TYPE}' and trashed = false and "
        "appProperties has { key='application' and "
        "value='telegram_archive_bot' } and appProperties has "
        "{ key='purpose' and value='archive_root' }"
    )
    folders: list[dict[str, str]] = []
    page_token: str | None = None

    while True:
        response = drive_service.files().list(
            q=query,
            spaces="drive",
            fields="nextPageToken, files(id, name, createdTime)",
            pageToken=page_token,
        ).execute()
        folders.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    if folders:
        folders.sort(
            key=lambda folder: (
                folder.get("createdTime", ""),
                folder["id"],
            )
        )
        if len(folders) > 1:
            logger.warning(
                "Multiple application archive folders found; using the oldest"
            )
        folder = _to_drive_folder(folders[0])
        logger.info("Archive folder found: %s", folder.id)
        return folder

    created = drive_service.files().create(
        body={
            "name": folder_name,
            "mimeType": FOLDER_MIME_TYPE,
            "appProperties": ARCHIVE_APP_PROPERTIES,
        },
        fields="id, name",
    ).execute()
    folder = _to_drive_folder(created)
    logger.info("Archive folder created: %s", folder.id)
    return folder
