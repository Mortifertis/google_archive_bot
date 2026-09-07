"""Tests for non-interactive Google authorization."""

from unittest.mock import patch

import pytest

from app.google_drive import GoogleAuthError, get_google_credentials


def test_non_interactive_auth_does_not_start_browser_flow(tmp_path) -> None:
    credentials_path = tmp_path / "credentials.json"
    credentials_path.write_text("{}", encoding="utf-8")

    with patch(
        "app.google_drive.InstalledAppFlow.from_client_secrets_file"
    ) as flow:
        with pytest.raises(GoogleAuthError, match="python -m app.google_auth"):
            get_google_credentials(
                str(credentials_path),
                str(tmp_path / "missing-token.json"),
                allow_interactive=False,
            )

    flow.assert_not_called()
