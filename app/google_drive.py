"""Google OAuth and Drive helpers for the archive folder setup."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from app.config import GoogleConfig
from app.document_builder import build_document_title, build_post_docx
from app.telegram_media import ArchivedMedia, DownloadedMedia, DownloadedPhoto
from app.telegram_parser import ForwardedPost

GOOGLE_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
]
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
GOOGLE_DOC_MIME_TYPE = "application/vnd.google-apps.document"
DOCX_MIME_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document"
)
ARCHIVE_APP_PROPERTIES = {
    "application": "telegram_archive_bot",
    "purpose": "archive_root",
}
MEDIA_FOLDER_APP_PROPERTIES = {
    "application": "telegram_archive_bot",
    "purpose": "archive_media_root",
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


@dataclass(frozen=True, slots=True)
class DriveDocument:
    """A native Google document created by the application."""

    id: str
    name: str
    web_url: str


@dataclass(frozen=True, slots=True)
class DriveMediaFile:
    """A binary Telegram media file stored in Google Drive."""

    id: str
    name: str
    mime_type: str
    web_url: str


def _save_credentials(credentials: Credentials, token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")


def get_google_credentials(
    credentials_path: str,
    token_path: str,
    *,
    allow_interactive: bool = True,
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

    if not allow_interactive:
        raise GoogleAuthError(
            "Google Drive is not authorized.\n"
            "Run: python -m app.google_auth"
        )

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
        response = (
            drive_service.files()
            .list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, createdTime)",
                pageToken=page_token,
            )
            .execute()
        )
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

    created = (
        drive_service.files()
        .create(
            body={
                "name": folder_name,
                "mimeType": FOLDER_MIME_TYPE,
                "appProperties": ARCHIVE_APP_PROPERTIES,
            },
            fields="id, name",
        )
        .execute()
    )
    folder = _to_drive_folder(created)
    logger.info("Archive folder created: %s", folder.id)
    return folder


def ensure_media_folder(
    drive_service: Any,
    archive_folder_id: str,
) -> DriveFolder:
    """Return the stable application Media folder below the archive root."""
    query = (
        f"mimeType = '{FOLDER_MIME_TYPE}' and trashed = false and "
        f"'{archive_folder_id}' in parents and appProperties has "
        "{ key='application' and value='telegram_archive_bot' } and "
        "appProperties has { key='purpose' and "
        "value='archive_media_root' }"
    )
    response = (
        drive_service.files()
        .list(
            q=query,
            spaces="drive",
            fields="files(id, name, createdTime)",
        )
        .execute()
    )
    folders = response.get("files", [])
    if folders:
        folders.sort(
            key=lambda folder: (folder.get("createdTime", ""), folder["id"])
        )
        if len(folders) > 1:
            logger.warning(
                "Multiple application Media folders found; using the oldest"
            )
        return _to_drive_folder(folders[0])
    created = (
        drive_service.files()
        .create(
            body={
                "name": "Media",
                "mimeType": FOLDER_MIME_TYPE,
                "parents": [archive_folder_id],
                "appProperties": MEDIA_FOLDER_APP_PROPERTIES,
            },
            fields="id, name",
        )
        .execute()
    )
    return _to_drive_folder(created)


def _media_extension(media: DownloadedMedia) -> str:
    if media.file_name:
        suffix = Path(media.file_name).suffix
        if suffix and suffix != "." and len(suffix) <= 16:
            return suffix.lower()
    return {"video/mp4": ".mp4", "image/gif": ".gif"}.get(
        media.mime_type or "", ".bin"
    )


def _safe_name_part(value: str) -> str:
    cleaned = "".join(
        " " if character == "/" or ord(character) < 32 else character
        for character in value
    )
    return " ".join(cleaned.split()) or "Telegram"


def build_media_file_name(
    post: ForwardedPost,
    media: DownloadedMedia,
    media_index: int,
) -> str:
    """Build a stable and human-readable Drive media filename."""
    date = (
        post.source_date.strftime("%Y-%m-%d")
        if post.source_date
        else "date"
    )
    channel = _safe_name_part(post.source_chat_title or "Telegram")
    message_id = post.source_message_id or "unknown"
    return (
        f"{date} — {channel} — {message_id} — "
        f"{media.kind}-{media_index:02d}{_media_extension(media)}"
    )


def _media_properties(
    post: ForwardedPost,
    media: DownloadedMedia,
    media_index: int,
) -> dict[str, str]:
    properties = {
        "application": "telegram_archive_bot",
        "purpose": "archived_media",
        "source_chat_id": str(post.source_chat_id),
        "source_message_id": str(post.source_message_id),
        "media_index": str(media_index),
        "media_kind": media.kind,
        "file_unique_id": media.file_unique_id,
    }
    if post.media_group_id is not None:
        properties["media_group_id"] = str(post.media_group_id)
    return properties


def find_archived_media(
    drive_service: Any,
    post: ForwardedPost,
    media: DownloadedMedia,
    media_index: int,
) -> DriveMediaFile | None:
    """Find the oldest active binary for a stable post media position."""
    properties = _media_properties(post, media, media_index)
    clauses = ["trashed = false"]
    for key in (
        "application",
        "purpose",
        "source_chat_id",
        "source_message_id",
        "media_index",
        "media_kind",
    ):
        clauses.append(
            "appProperties has { key='"
            f"{key}' and value='{properties[key]}' }}"
        )
    response = (
        drive_service.files()
        .list(
            q=" and ".join(clauses),
            spaces="drive",
            fields="files(id, name, mimeType, createdTime)",
        )
        .execute()
    )
    files = response.get("files", [])
    if not files:
        return None
    files.sort(key=lambda item: (item.get("createdTime", ""), item["id"]))
    if len(files) > 1:
        logger.warning("Multiple archived media files found; using the oldest")
    item = files[0]
    return DriveMediaFile(
        id=item["id"],
        name=item["name"],
        mime_type=item.get("mimeType", media.mime_type or ""),
        web_url=f"https://drive.google.com/file/d/{item['id']}/view",
    )


def archive_media_file(
    drive_service: Any,
    media_folder_id: str,
    post: ForwardedPost,
    media: DownloadedMedia,
    media_index: int,
) -> DriveMediaFile:
    """Reuse or upload one binary video/animation entirely from memory."""
    existing = find_archived_media(
        drive_service, post, media, media_index
    )
    if existing:
        return existing
    if media.data is None:
        raise ValueError("Cannot upload unavailable Telegram media")
    mime_type = media.mime_type or (
        "video/mp4" if media.kind == "video" else "application/octet-stream"
    )
    name = build_media_file_name(post, media, media_index)
    upload = MediaIoBaseUpload(
        BytesIO(media.data),
        mimetype=mime_type,
        resumable=len(media.data) > 5 * 1024 * 1024,
    )
    created = (
        drive_service.files()
        .create(
            body={
                "name": name,
                "parents": [media_folder_id],
                "appProperties": _media_properties(
                    post, media, media_index
                ),
            },
            media_body=upload,
            fields="id, name, mimeType",
        )
        .execute()
    )
    file_id = created["id"]
    return DriveMediaFile(
        id=file_id,
        name=created.get("name", name),
        mime_type=created.get("mimeType", mime_type),
        web_url=f"https://drive.google.com/file/d/{file_id}/view",
    )


def create_google_document(
    drive_service: Any,
    archive_folder_id: str,
    title: str,
    docx_stream: BytesIO,
    app_properties: dict[str, str] | None = None,
) -> DriveDocument:
    """Upload DOCX content and import it as a native Google document."""
    docx_stream.seek(0)
    body: dict[str, Any] = {
        "name": title,
        "mimeType": GOOGLE_DOC_MIME_TYPE,
        "parents": [archive_folder_id],
    }
    if app_properties:
        body["appProperties"] = {
            key: str(value) for key, value in app_properties.items()
        }
    media = MediaIoBaseUpload(
        docx_stream,
        mimetype=DOCX_MIME_TYPE,
        resumable=False,
    )
    created = (
        drive_service.files()
        .create(
            body=body,
            media_body=media,
            fields="id, name",
        )
        .execute()
    )
    file_id = created["id"]
    return DriveDocument(
        id=file_id,
        name=created["name"],
        web_url=f"https://docs.google.com/document/d/{file_id}/edit",
    )


def find_archived_document(
    drive_service: Any,
    source_chat_id: int,
    source_message_id: int,
) -> DriveDocument | None:
    """Find the oldest active document for one Telegram source post."""
    query = (
        "trashed = false and "
        f"mimeType = '{GOOGLE_DOC_MIME_TYPE}' and "
        "appProperties has { key='application' and "
        "value='telegram_archive_bot' } and "
        "appProperties has { key='purpose' and "
        "value='archived_post' } and "
        "appProperties has { key='source_chat_id' and "
        f"value='{source_chat_id}' }} and "
        "appProperties has { key='source_message_id' and "
        f"value='{source_message_id}' }}"
    )
    documents: list[dict[str, str]] = []
    page_token: str | None = None

    while True:
        response = (
            drive_service.files()
            .list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, createdTime)",
                pageToken=page_token,
            )
            .execute()
        )
        documents.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    if not documents:
        return None

    documents.sort(
        key=lambda document: (
            document.get("createdTime", ""),
            document["id"],
        )
    )
    if len(documents) > 1:
        logger.warning(
            "Multiple archived documents found for Telegram source: "
            "chat_id=%s, message_id=%s",
            source_chat_id,
            source_message_id,
        )

    document = documents[0]
    document_id = document["id"]
    return DriveDocument(
        id=document_id,
        name=document["name"],
        web_url=(
            f"https://docs.google.com/document/d/{document_id}/edit"
        ),
    )


def find_existing_archived_post(
    post: ForwardedPost,
    google_config: GoogleConfig,
) -> DriveDocument | None:
    """Find a post by stable Telegram coordinates when both are known."""
    if post.source_chat_id is None or post.source_message_id is None:
        return None

    credentials = get_google_credentials(
        google_config.credentials_path,
        google_config.token_path,
        allow_interactive=False,
    )
    drive_service = build_drive_service(credentials)
    return find_archived_document(
        drive_service,
        post.source_chat_id,
        post.source_message_id,
    )


def archive_forwarded_post(
    post: ForwardedPost,
    google_config: GoogleConfig,
    photos: Sequence[DownloadedPhoto | DownloadedMedia] = (),
) -> DriveDocument:
    """Synchronously archive one post using a fresh Drive service."""
    credentials = get_google_credentials(
        google_config.credentials_path,
        google_config.token_path,
        allow_interactive=False,
    )
    drive_service = build_drive_service(credentials)
    folder = ensure_archive_folder(
        drive_service,
        google_config.archive_folder_name,
    )
    properties = {
        "application": "telegram_archive_bot",
        "purpose": "archived_post",
    }
    if post.source_chat_id is not None:
        properties["source_chat_id"] = str(post.source_chat_id)
    if post.source_message_id is not None:
        properties["source_message_id"] = str(post.source_message_id)
    if post.media_group_id is not None:
        properties["media_group_id"] = str(post.media_group_id)
    properties["photo_count"] = str(post.photo_count)
    properties["video_count"] = str(post.video_count)
    properties["animation_count"] = str(post.animation_count)
    properties["media_count"] = str(post.media_count)

    document_media: list[DownloadedPhoto | ArchivedMedia] = []
    media_folder = None
    for index, item in enumerate(photos, start=1):
        if isinstance(item, DownloadedPhoto):
            document_media.append(item)
            continue
        if item.kind == "photo":
            document_media.append(
                ArchivedMedia(
                    kind="photo",
                    preview_data=item.data,
                    width=item.width,
                    height=item.height,
                    duration=None,
                    file_size=item.file_size,
                    mime_type=item.mime_type,
                )
            )
            continue
        drive_file = None
        if item.data is not None:
            if media_folder is None:
                media_folder = ensure_media_folder(drive_service, folder.id)
            drive_file = archive_media_file(
                drive_service,
                media_folder.id,
                post,
                item,
                index,
            )
        document_media.append(
            ArchivedMedia(
                kind=item.kind,
                preview_data=item.preview_data,
                width=item.width,
                height=item.height,
                duration=item.duration,
                file_size=item.file_size,
                mime_type=item.mime_type,
                drive_web_url=(drive_file.web_url if drive_file else None),
                unavailable_reason=item.unavailable_reason,
            )
        )

    return create_google_document(
        drive_service,
        folder.id,
        build_document_title(post),
        build_post_docx(post, document_media),
        properties,
    )
