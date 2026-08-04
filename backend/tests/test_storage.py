import os
from pathlib import Path

from app.core.config import settings
from app.core.storage import get_download_url, upload_file_object


def test_upload_file_object_writes_local_file(tmp_path: Path) -> None:
    settings.upload_dir = str(tmp_path / "uploads")
    object_key = "ticket-1/test-file.txt"
    contents = b"hello world"
    path = upload_file_object(object_key, contents, "text/plain")

    assert os.path.exists(path)
    with open(path, "rb") as handle:
        assert handle.read() == contents


def test_get_download_url_returns_local_path() -> None:
    path = get_download_url("ticket-1/test-file.txt")
    assert path == "ticket-1/test-file.txt"
