"""Comprehensive tests for services/mlops/data_manifest.py."""

import json
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# services.mlops.data_manifest does ``import mlflow`` at module import time, but
# mlflow is only used inside log_to_mlflow (not exercised by these tests, which
# cover hashing / scanning / manifest generation / validation only). Provide a
# lightweight stub so the module imports even when mlflow isn't installed. If a
# real mlflow is present, prefer it and don't shadow it.
try:  # pragma: no cover - depends on environment
    import mlflow  # noqa: F401
except ImportError:
    sys.modules.setdefault("mlflow", types.ModuleType("mlflow"))

from services.mlops.data_manifest import DataManifestGenerator  # noqa: E402


@pytest.fixture
def gen():
    return DataManifestGenerator(hash_algorithms=["md5"])


@pytest.fixture
def data_dir(tmp_path):
    (tmp_path / "a.txt").write_text("hello world")
    (tmp_path / "b.txt").write_text("second file content")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.txt").write_text("nested file")
    return tmp_path


class TestHashing:
    def test_calculate_file_hash(self, gen, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("hello")
        import hashlib
        assert gen.calculate_file_hash(f, "md5") == hashlib.md5(b"hello").hexdigest()

    def test_unsupported_algorithm(self, gen, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("hi")
        with pytest.raises(ValueError):
            gen.calculate_file_hash(f, "nope")

    def test_sha256(self, tmp_path):
        g = DataManifestGenerator(hash_algorithms=["sha256"])
        f = tmp_path / "x.txt"
        f.write_text("data")
        import hashlib
        assert g.calculate_file_hash(f, "sha256") == hashlib.sha256(b"data").hexdigest()


class TestFormatSize:
    @pytest.mark.parametrize("size,expected", [
        (0, "0.0 B"),
        (512, "512.0 B"),
        (1024, "1.0 KB"),
        (1024 * 1024, "1.0 MB"),
        (1024 ** 3, "1.0 GB"),
    ])
    def test_format(self, gen, size, expected):
        assert gen._format_size(size) == expected


class TestFileMetadata:
    def test_metadata_includes_hashes(self, gen, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("content here")
        meta = gen.get_file_metadata(f)
        assert meta["size_bytes"] == len("content here")
        assert meta["is_file"] is True
        assert "md5" in meta["hashes"]
        assert meta["name"] == "x.txt"


class TestScanDirectory:
    def test_scan_finds_files(self, gen, data_dir):
        files = gen.scan_directory(data_dir)
        names = {f.name for f in files}
        assert {"a.txt", "b.txt", "c.txt"}.issubset(names)

    def test_missing_directory(self, gen, tmp_path):
        with pytest.raises(FileNotFoundError):
            gen.scan_directory(tmp_path / "nope")

    def test_not_a_directory(self, gen, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("hi")
        with pytest.raises(ValueError):
            gen.scan_directory(f)

    def test_max_files(self, gen, data_dir):
        files = gen.scan_directory(data_dir, max_files=2)
        assert len(files) == 2


class TestGenerateManifest:
    def test_directory_manifest(self, gen, data_dir):
        manifest = gen.generate_manifest(data_dir)
        assert manifest["manifest_version"] == "1.0"
        assert manifest["summary"]["processed_files"] == 3
        assert manifest["summary"]["total_size_bytes"] > 0
        assert len(manifest["files"]) == 3

    def test_single_file_manifest(self, gen, tmp_path):
        f = tmp_path / "only.txt"
        f.write_text("just one")
        manifest = gen.generate_manifest(f)
        assert manifest["summary"]["total_files"] == 1

    def test_invalid_path(self, gen, tmp_path):
        with pytest.raises(ValueError):
            gen.generate_manifest(tmp_path / "does-not-exist")

    def test_custom_metadata(self, gen, data_dir):
        manifest = gen.generate_manifest(data_dir, metadata={"version": "v1"})
        assert manifest["metadata"]["version"] == "v1"


class TestSaveManifest:
    def test_save_creates_json(self, gen, data_dir, tmp_path):
        manifest = gen.generate_manifest(data_dir)
        out = tmp_path / "out" / "manifest.json"
        result_path = gen.save_manifest(manifest, out)
        assert result_path.exists()
        loaded = json.loads(out.read_text())
        assert loaded["manifest_version"] == "1.0"


class TestValidateManifest:
    def test_valid_unchanged(self, gen, data_dir):
        manifest = gen.generate_manifest(data_dir)
        result = gen.validate_manifest(manifest, data_dir)
        assert result["valid"] is True
        assert result["found_files"] == 3
        assert result["missing_files"] == []

    def test_detects_missing_file(self, gen, data_dir):
        manifest = gen.generate_manifest(data_dir)
        (data_dir / "a.txt").unlink()
        result = gen.validate_manifest(manifest, data_dir)
        assert result["valid"] is False
        assert len(result["missing_files"]) == 1

    def test_detects_modified_content(self, gen, data_dir):
        manifest = gen.generate_manifest(data_dir)
        (data_dir / "a.txt").write_text("completely different content now longer")
        result = gen.validate_manifest(manifest, data_dir)
        assert result["valid"] is False
        # either size mismatch or hash mismatch flags it
        assert result["size_mismatches"] or result["hash_mismatches"]
