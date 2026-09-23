import importlib
import sys
from pathlib import Path

import pytest


imagebackup = importlib.import_module("imagebackup.main")


def test_finds_supported_files_case_insensitively_and_ignores_other_files(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / "photo.JPG").write_bytes(b"one")
    (nested / "raw.CR2").write_bytes(b"two")
    (tmp_path / "notes.txt").write_bytes(b"ignore")

    files, total_size = imagebackup.get_transfer_list(str(tmp_path))

    assert total_size == 6
    assert {Path(path).name for path, _, _ in files} == {"photo.JPG", "raw.CR2"}


def test_keeps_file_record_when_size_cannot_be_read(tmp_path, monkeypatch):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"data")
    monkeypatch.setattr(imagebackup.os.path, "getsize", lambda _: (_ for _ in ()).throw(OSError()))

    files, total_size = imagebackup.get_transfer_list(str(tmp_path))

    assert len(files) == 1
    assert Path(files[0][0]).name == "photo.jpg"
    assert total_size == 0


def test_uses_default_arguments(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["imagebackup"])

    args = imagebackup.parse_args()

    assert args.source == imagebackup.DEFAULT_SOURCE_DIR
    assert args.dest == imagebackup.DEFAULT_DEST_BASE
    assert args.port == 8000
    assert args.host == "0.0.0.0"


def test_accepts_custom_arguments(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "imagebackup",
            "--source",
            "/photos",
            "-d",
            "/backups",
            "-p",
            "8080",
            "--host",
            "127.0.0.1",
        ],
    )

    args = imagebackup.parse_args()

    assert vars(args) == {
        "source": "/photos",
        "dest": "/backups",
        "port": 8080,
        "host": "127.0.0.1",
    }


@pytest.fixture
def client():
    original_status = imagebackup.status_data.copy()
    imagebackup.start_requested.clear()
    imagebackup.stop_requested.clear()
    yield imagebackup.app.test_client()
    imagebackup.status_data.clear()
    imagebackup.status_data.update(original_status)
    imagebackup.start_requested.clear()
    imagebackup.stop_requested.clear()


def test_status_returns_current_status(client):
    imagebackup.status_data["phase"] = "COPYING"

    response = client.get("/status")

    assert response.status_code == 200
    assert response.get_json()["phase"] == "COPYING"


def test_start_rejects_unready_media_and_accepts_ready_media(client):
    response = client.post("/start")
    assert response.status_code == 400
    assert response.get_json()["success"] is False

    imagebackup.status_data["media_ready"] = True
    response = client.post("/start")
    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert imagebackup.start_requested.is_set()


def test_start_rejects_an_active_backup(client):
    imagebackup.status_data.update(active=True, media_ready=True)

    response = client.post("/start")

    assert response.status_code == 400
    assert response.get_json()["message"] == "Backup is already running"


def test_stop_requires_an_active_backup_and_sets_stop_event(client):
    response = client.post("/stop")
    assert response.status_code == 400

    imagebackup.status_data["active"] = True
    response = client.post("/stop")

    assert response.status_code == 200
    assert imagebackup.stop_requested.is_set()
