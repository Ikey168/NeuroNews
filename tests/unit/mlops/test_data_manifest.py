"""Tests for services/mlops/data_manifest.py (pure filesystem logic)."""

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

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
    (sub / "c.txt").write_text("nested")
    return tmp_path


class TestInit:
    def test_default_algorithms(self):
        g = DataManifestGenerator()
        assert "md5" in g.hash_algorithms and "sha256" in g.hash_algorithms

    def test_invalid_algorithm_raises(self):
        with pytest.raises(ValueError):
            DataManifestGenerator(hash_algorithms=["crc32"])


class TestHashAndMetadata:
    def test_calculate_file_hash(self, gen, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("content")
        h = gen.calculate_file_hash(f, "md5")
        assert len(h) == 32
        # deterministic
        assert gen.calculate_file_hash(f, "md5") == h

    def test_unsupported_algorithm(self, gen, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("c")
        with pytest.raises(ValueError):
            gen.calculate_file_hash(f, "bogus")

    def test_get_file_metadata(self, gen, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("hello")
        meta = gen.get_file_metadata(f)
        assert meta["name"] == "x.txt"
        assert meta["size_bytes"] == 5
        assert meta["is_file"] is True
        assert "md5" in meta["hashes"]

    @pytest.mark.parametrize("size,unit", [
        (500, "B"), (2048, "KB"), (5 * 1024 * 1024, "MB"),
    ])
    def test_format_size(self, gen, size, unit):
        assert unit in gen._format_size(size)


class TestScanDirectory:
    def test_scan_finds_files(self, gen, data_dir):
        files = gen.scan_directory(data_dir)
        names = {f.name for f in files}
        assert {"a.txt", "b.txt", "c.txt"} <= names

    def test_scan_missing_dir_raises(self, gen, tmp_path):
        with pytest.raises(FileNotFoundError):
            gen.scan_directory(tmp_path / "nope")

    def test_scan_not_a_directory(self, gen, tmp_path):
        f = tmp_path / "x.txt"
        f.write_text("c")
        with pytest.raises(ValueError):
            gen.scan_directory(f)

    def test_max_files_limit(self, gen, data_dir):
        files = gen.scan_directory(data_dir, max_files=1)
        assert len(files) == 1


class TestManifest:
    def test_generate_for_directory(self, gen, data_dir):
        manifest = gen.generate_manifest(data_dir)
        assert manifest["manifest_version"] == "1.0"
        assert manifest["summary"]["processed_files"] == 3
        assert manifest["summary"]["total_size_bytes"] > 0

    def test_generate_for_single_file(self, gen, tmp_path):
        f = tmp_path / "only.txt"
        f.write_text("data")
        manifest = gen.generate_manifest(f)
        assert manifest["summary"]["total_files"] == 1

    def test_save_manifest(self, gen, data_dir, tmp_path):
        manifest = gen.generate_manifest(data_dir)
        out = tmp_path / "out" / "manifest.json"
        saved = gen.save_manifest(manifest, out)
        assert Path(saved).exists()
        assert json.loads(out.read_text())["manifest_version"] == "1.0"

    def test_validate_manifest_valid(self, gen, data_dir):
        manifest = gen.generate_manifest(data_dir)
        result = gen.validate_manifest(manifest, data_dir)
        assert result["valid"] is True
        assert result["found_files"] == 3

    def test_validate_detects_missing(self, gen, data_dir):
        manifest = gen.generate_manifest(data_dir)
        (data_dir / "a.txt").unlink()
        result = gen.validate_manifest(manifest, data_dir)
        assert result["valid"] is False
        assert len(result["missing_files"]) == 1
