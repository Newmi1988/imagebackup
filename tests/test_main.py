import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


imagebackup = importlib.import_module("imagebackup.main")


class TransferListTests(unittest.TestCase):
    def test_finds_supported_files_case_insensitively_and_ignores_other_files(self):
        with tempfile.TemporaryDirectory() as source:
            source_path = Path(source)
            nested = source_path / "nested"
            nested.mkdir()
            (source_path / "photo.JPG").write_bytes(b"one")
            (nested / "raw.CR2").write_bytes(b"two")
            (source_path / "notes.txt").write_bytes(b"ignore")

            files, total_size = imagebackup.get_transfer_list(source)

        self.assertEqual(total_size, 6)
        self.assertEqual({Path(path).name for path, _, _ in files}, {"photo.JPG", "raw.CR2"})

    def test_keeps_file_record_when_size_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as source:
            photo = Path(source) / "photo.jpg"
            photo.write_bytes(b"data")
            with patch.object(imagebackup.os.path, "getsize", side_effect=OSError):
                files, total_size = imagebackup.get_transfer_list(source)

        self.assertEqual(len(files), 1)
        self.assertEqual(Path(files[0][0]).name, "photo.jpg")
        self.assertEqual(total_size, 0)


class ParseArgsTests(unittest.TestCase):
    def test_uses_defaults(self):
        with patch.object(sys, "argv", ["imagebackup"]):
            args = imagebackup.parse_args()

        self.assertEqual(args.source, imagebackup.DEFAULT_SOURCE_DIR)
        self.assertEqual(args.dest, imagebackup.DEFAULT_DEST_BASE)
        self.assertEqual(args.port, 8000)
        self.assertEqual(args.host, "0.0.0.0")

    def test_accepts_custom_values(self):
        with patch.object(
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
        ):
            args = imagebackup.parse_args()

        self.assertEqual(vars(args), {
            "source": "/photos",
            "dest": "/backups",
            "port": 8080,
            "host": "127.0.0.1",
        })


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.original_status = imagebackup.status_data.copy()
        imagebackup.start_requested.clear()
        imagebackup.stop_requested.clear()
        self.client = imagebackup.app.test_client()

    def tearDown(self):
        imagebackup.status_data.clear()
        imagebackup.status_data.update(self.original_status)
        imagebackup.start_requested.clear()
        imagebackup.stop_requested.clear()

    def test_status_returns_current_status(self):
        imagebackup.status_data["phase"] = "COPYING"

        response = self.client.get("/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["phase"], "COPYING")

    def test_start_rejects_unready_media_and_accepts_ready_media(self):
        response = self.client.post("/start")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])

        imagebackup.status_data["media_ready"] = True
        response = self.client.post("/start")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        self.assertTrue(imagebackup.start_requested.is_set())

    def test_start_rejects_an_active_backup(self):
        imagebackup.status_data.update(active=True, media_ready=True)

        response = self.client.post("/start")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["message"], "Backup is already running")

    def test_stop_requires_an_active_backup_and_sets_stop_event(self):
        response = self.client.post("/stop")
        self.assertEqual(response.status_code, 400)

        imagebackup.status_data["active"] = True
        response = self.client.post("/stop")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(imagebackup.stop_requested.is_set())


if __name__ == "__main__":
    unittest.main()
