"""
Coverage-focused tests for FileSystemConnector.

Uses real temporary directories/files (tmp_path) so the aiofiles read/write
paths are exercised end to end with assertions on the returned records.
"""

import json

import pytest

# aiofiles and yaml are hard imports of the module under test; both present.
pytest.importorskip("aiofiles")
pytest.importorskip("yaml")

from src.scraper.extensions.connectors.filesystem_connector import (
    FileSystemConnector,
)
from src.scraper.extensions.connectors.base import ConnectionError as ConnConnectionError


async def _connected(base_path):
    c = FileSystemConnector({"base_path": str(base_path), "format": "auto"})
    ok = await c.connect()
    assert ok is True
    return c


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


def test_validate_config_existing_path(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path)})
    assert c.validate_config() is True


def test_validate_config_missing_field():
    c = FileSystemConnector({})
    assert c.validate_config() is False


def test_validate_config_parent_exists(tmp_path):
    # Path itself does not exist but parent does -> still valid.
    target = tmp_path / "not_yet"
    c = FileSystemConnector({"base_path": str(target)})
    assert c.validate_config() is True


def test_validate_config_nonexistent_parent(tmp_path):
    target = tmp_path / "a" / "b" / "c"
    c = FileSystemConnector({"base_path": str(target)})
    assert c.validate_config() is False


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_success(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path)})
    assert await c.connect() is True
    assert c.is_connected is True


@pytest.mark.asyncio
async def test_connect_missing_path_fails(tmp_path):
    missing = tmp_path / "does_not_exist"
    c = FileSystemConnector({"base_path": str(missing)})
    assert await c.connect() is False
    assert c.is_connected is False
    assert c.last_error is not None
    assert "does not exist" in str(c.last_error)


@pytest.mark.asyncio
async def test_connect_creates_missing_when_configured(tmp_path):
    new_dir = tmp_path / "created"
    c = FileSystemConnector(
        {"base_path": str(new_dir), "create_if_missing": True}
    )
    assert await c.connect() is True
    assert new_dir.exists()
    assert c.is_connected is True


@pytest.mark.asyncio
async def test_disconnect_sets_disconnected(tmp_path):
    c = await _connected(tmp_path)
    await c.disconnect()
    assert c.is_connected is False


# ---------------------------------------------------------------------------
# fetch_data / _read_file across formats
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_json_list(tmp_path):
    (tmp_path / "data.json").write_text(json.dumps([{"a": 1}, {"a": 2}]))
    c = await _connected(tmp_path)
    records = await c.fetch_data("*.json")
    assert {r["a"] for r in records} == {1, 2}


@pytest.mark.asyncio
async def test_fetch_json_object_wrapped_in_list(tmp_path):
    (tmp_path / "one.json").write_text(json.dumps({"k": "v"}))
    c = await _connected(tmp_path)
    records = await c.fetch_data("*.json")
    assert records == [{"k": "v"}]


@pytest.mark.asyncio
async def test_fetch_json_scalar_wrapped_in_data_key(tmp_path):
    (tmp_path / "scalar.json").write_text(json.dumps(42))
    c = await _connected(tmp_path)
    records = await c.fetch_data("scalar.json")
    assert records == [{"data": 42}]


@pytest.mark.asyncio
async def test_fetch_csv(tmp_path):
    (tmp_path / "rows.csv").write_text("name,age\nAlice,30\nBob,25\n")
    c = await _connected(tmp_path)
    records = await c.fetch_data("*.csv")
    assert len(records) == 2
    assert records[0]["name"] == "Alice"
    assert records[0]["age"] == "30"
    assert records[1]["name"] == "Bob"


@pytest.mark.asyncio
async def test_fetch_yaml_list(tmp_path):
    (tmp_path / "cfg.yaml").write_text("- x: 1\n- x: 2\n")
    c = await _connected(tmp_path)
    records = await c.fetch_data("*.yaml")
    assert [r["x"] for r in records] == [1, 2]


@pytest.mark.asyncio
async def test_fetch_yaml_dict(tmp_path):
    (tmp_path / "cfg.yml").write_text("name: test\nvalue: 7\n")
    c = await _connected(tmp_path)
    records = await c.fetch_data("*.yml")
    assert records == [{"name": "test", "value": 7}]


@pytest.mark.asyncio
async def test_fetch_yaml_scalar_wrapped(tmp_path):
    (tmp_path / "scalar.yaml").write_text("just a string\n")
    c = await _connected(tmp_path)
    records = await c.fetch_data("scalar.yaml")
    assert records == [{"data": "just a string"}]


@pytest.mark.asyncio
async def test_fetch_txt_lines(tmp_path):
    (tmp_path / "notes.txt").write_text("line one\n\nline two\n")
    c = await _connected(tmp_path)
    records = await c.fetch_data("*.txt")
    # Blank lines skipped; two content lines remain.
    assert len(records) == 2
    assert records[0]["line"] == "line one"
    assert records[0]["line_number"] == 1
    assert records[1]["line"] == "line two"
    assert records[1]["line_number"] == 3
    assert records[0]["file"].endswith("notes.txt")


@pytest.mark.asyncio
async def test_fetch_unknown_format_returns_raw_content(tmp_path):
    # format forced so _detect_file_format returns the configured value.
    (tmp_path / "blob.dat").write_text("weird content")
    c = FileSystemConnector({"base_path": str(tmp_path), "format": "binaryish"})
    assert await c.connect() is True
    records = await c.fetch_data("blob.dat")
    assert records == [
        {
            "content": "weird content",
            "file": str(tmp_path / "blob.dat"),
            "format": "binaryish",
        }
    ]


@pytest.mark.asyncio
async def test_fetch_recursive_finds_nested(tmp_path):
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "deep.json").write_text(json.dumps({"deep": True}))
    c = await _connected(tmp_path)
    records = await c.fetch_data("*.json", recursive=True)
    assert records == [{"deep": True}]
    # Non-recursive should not find the nested file.
    assert await c.fetch_data("*.json", recursive=False) == []


@pytest.mark.asyncio
async def test_read_file_bad_json_returns_empty(tmp_path):
    (tmp_path / "broken.json").write_text("{not valid json")
    c = await _connected(tmp_path)
    records = await c.fetch_data("broken.json")
    # _read_file swallows the parse error and returns [].
    assert records == []


@pytest.mark.asyncio
async def test_fetch_data_not_connected_raises(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path)})
    with pytest.raises(ConnConnectionError, match="Not connected"):
        await c.fetch_data("*")


class _ExplodingPath:
    """Stand-in for _base_path whose glob/rglob raise."""

    def glob(self, pattern):
        raise OSError("glob failed")

    def rglob(self, pattern):
        raise OSError("rglob failed")


@pytest.mark.asyncio
async def test_fetch_data_glob_exception_wrapped(tmp_path):
    c = await _connected(tmp_path)
    c._base_path = _ExplodingPath()
    with pytest.raises(ConnConnectionError, match="Failed to fetch filesystem data"):
        await c.fetch_data("*")
    assert c.last_error is not None


# ---------------------------------------------------------------------------
# _detect_file_format
# ---------------------------------------------------------------------------


def test_detect_file_format_uses_configured(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path), "format": "json"})
    from pathlib import Path

    assert c._detect_file_format(Path("anything.csv")) == "json"


def test_detect_file_format_auto_by_extension(tmp_path):
    from pathlib import Path

    c = FileSystemConnector({"base_path": str(tmp_path), "format": "auto"})
    assert c._detect_file_format(Path("f.json")) == "json"
    assert c._detect_file_format(Path("f.csv")) == "csv"
    assert c._detect_file_format(Path("f.yaml")) == "yaml"
    assert c._detect_file_format(Path("f.yml")) == "yaml"
    assert c._detect_file_format(Path("f.txt")) == "txt"
    assert c._detect_file_format(Path("f.log")) == "txt"
    assert c._detect_file_format(Path("f.unknown")) == "txt"  # fallback


# ---------------------------------------------------------------------------
# write_data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_json_roundtrip(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path), "format": "json"})
    assert await c.connect() is True
    payload = [{"id": 1, "name": "a"}]
    assert await c.write_data(payload, "out.json") is True
    written = json.loads((tmp_path / "out.json").read_text())
    assert written == payload


@pytest.mark.asyncio
async def test_write_csv(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path), "format": "csv"})
    assert await c.connect() is True
    assert await c.write_data([{"a": "1", "b": "2"}], "out.csv") is True
    text = (tmp_path / "out.csv").read_text()
    assert "a,b" in text
    assert "1,2" in text


@pytest.mark.asyncio
async def test_write_csv_empty_data(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path), "format": "csv"})
    assert await c.connect() is True
    assert await c.write_data([], "empty.csv") is True
    assert (tmp_path / "empty.csv").read_text() == ""


@pytest.mark.asyncio
async def test_write_yaml(tmp_path):
    import yaml as _yaml

    c = FileSystemConnector({"base_path": str(tmp_path), "format": "yaml"})
    assert await c.connect() is True
    assert await c.write_data([{"k": "v"}], "out.yaml") is True
    loaded = _yaml.safe_load((tmp_path / "out.yaml").read_text())
    assert loaded == [{"k": "v"}]


@pytest.mark.asyncio
async def test_write_default_format_is_json(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path), "format": "weird"})
    assert await c.connect() is True
    assert await c.write_data([{"x": 1}], "out.bin") is True
    # Falls through to JSON serialization.
    assert json.loads((tmp_path / "out.bin").read_text()) == [{"x": 1}]


@pytest.mark.asyncio
async def test_write_format_override(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path), "format": "json"})
    assert await c.connect() is True
    assert await c.write_data([{"a": "1"}], "override.csv", file_format="csv") is True
    assert "a" in (tmp_path / "override.csv").read_text()


@pytest.mark.asyncio
async def test_write_not_connected_raises(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path)})
    with pytest.raises(ConnConnectionError, match="Not connected"):
        await c.write_data([{"a": 1}], "x.json")


@pytest.mark.asyncio
async def test_write_failure_returns_false(tmp_path, monkeypatch):
    c = FileSystemConnector({"base_path": str(tmp_path), "format": "json"})
    assert await c.connect() is True

    import src.scraper.extensions.connectors.filesystem_connector as mod

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(mod.aiofiles, "open", boom)
    assert await c.write_data([{"a": 1}], "fail.json") is False
    assert c.last_error is not None


# ---------------------------------------------------------------------------
# validate_data_format
# ---------------------------------------------------------------------------


def test_validate_data_format(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path)})
    assert c.validate_data_format({"a": 1}) is True
    assert c.validate_data_format({}) is False
    assert c.validate_data_format(["not", "a", "dict"]) is False
    assert c.validate_data_format("str") is False


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_files_returns_metadata(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "b.txt").write_text("hello")
    c = await _connected(tmp_path)
    files = await c.list_files("*")
    names = {f["name"] for f in files}
    assert names == {"a.json", "b.txt"}
    a_meta = next(f for f in files if f["name"] == "a.json")
    assert a_meta["format"] == "json"
    assert a_meta["extension"] == ".json"
    assert a_meta["size"] >= 0
    assert "modified" in a_meta
    assert a_meta["path"].endswith("a.json")


@pytest.mark.asyncio
async def test_list_files_recursive(tmp_path):
    sub = tmp_path / "s"
    sub.mkdir()
    (sub / "n.csv").write_text("x\n1\n")
    c = await _connected(tmp_path)
    files = await c.list_files("*.csv", recursive=True)
    assert len(files) == 1
    assert files[0]["name"] == "n.csv"


@pytest.mark.asyncio
async def test_list_files_not_connected_raises(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path)})
    with pytest.raises(ConnConnectionError, match="Not connected"):
        await c.list_files()


@pytest.mark.asyncio
async def test_list_files_exception_wrapped(tmp_path):
    c = await _connected(tmp_path)
    c._base_path = _ExplodingPath()
    with pytest.raises(ConnConnectionError, match="Failed to list files"):
        await c.list_files("*")


# ---------------------------------------------------------------------------
# get_file_info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_file_info(tmp_path):
    f = tmp_path / "info.json"
    f.write_text(json.dumps({"a": 1}))
    c = await _connected(tmp_path)
    info = await c.get_file_info("info.json")
    assert info["name"] == "info.json"
    assert info["format"] == "json"
    assert info["extension"] == ".json"
    assert info["is_readable"] is True
    assert isinstance(info["is_writable"], bool)
    assert info["size"] > 0
    assert "created" in info


@pytest.mark.asyncio
async def test_get_file_info_missing_raises(tmp_path):
    c = await _connected(tmp_path)
    with pytest.raises(ConnConnectionError, match="Failed to get file info"):
        await c.get_file_info("nope.json")
    assert c.last_error is not None


@pytest.mark.asyncio
async def test_get_file_info_not_connected_raises(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path)})
    with pytest.raises(ConnConnectionError, match="Not connected"):
        await c.get_file_info("x.json")


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_file_success(tmp_path):
    f = tmp_path / "gone.txt"
    f.write_text("bye")
    c = await _connected(tmp_path)
    assert await c.delete_file("gone.txt") is True
    assert not f.exists()


@pytest.mark.asyncio
async def test_delete_file_missing_returns_false(tmp_path):
    c = await _connected(tmp_path)
    assert await c.delete_file("never.txt") is False


@pytest.mark.asyncio
async def test_delete_file_not_connected_raises(tmp_path):
    c = FileSystemConnector({"base_path": str(tmp_path)})
    with pytest.raises(ConnConnectionError, match="Not connected"):
        await c.delete_file("x.txt")


@pytest.mark.asyncio
async def test_delete_file_exception_returns_false(tmp_path, monkeypatch):
    f = tmp_path / "locked.txt"
    f.write_text("x")
    c = await _connected(tmp_path)

    from pathlib import Path

    def boom(self):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "unlink", boom)
    assert await c.delete_file("locked.txt") is False
    assert c.last_error is not None
