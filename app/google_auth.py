"""Standalone command for authorizing and initializing Google Drive."""

import logging

from app.config import load_google_config
from app.google_drive import (build_drive_service, ensure_archive_folder,
                              get_google_credentials)

logger = logging.getLogger(__name__)


def main() -> int:
    """Authorize Google Drive and print the archive folder details."""
    print("Starting Google authorization...")
    try:
        config = load_google_config()
        credentials = get_google_credentials(
            config.credentials_path,
            config.token_path,
        )
        drive_service = build_drive_service(credentials)
        folder = ensure_archive_folder(
            drive_service,
            config.archive_folder_name,
        )
    except Exception as error:
        logger.debug("Google authorization failed", exc_info=True)
        print(f"Google authorization failed: {error}")
        return 1

    print("Google Drive connected successfully.")
    print("\nArchive folder:")
    print(f"Name: {folder.name}")
    print(f"ID: {folder.id}")
    print(f"URL: {folder.web_url}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    raise SystemExit(main())
