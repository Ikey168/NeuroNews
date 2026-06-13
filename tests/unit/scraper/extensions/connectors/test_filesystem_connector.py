"""
Test cases for filesystem connector functionality.
"""

import pytest
import asyncio
import tempfile
import json
import csv
import yaml
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from src.scraper.extensions.connectors.filesystem_connector import FileSystemConnector
from src.scraper.extensions.connectors.base import ConnectionError


class TestFileSystemConnector:
    """Test cases for FileSystemConnector class."""

    def test_init(self):
        """Test filesystem connector initialization."""
        config = {
            "base_path": "/tmp/test",
            "format": "json"
        }
        
        connector = FileSystemConnector(config)
        
        assert connector.config == config
        assert connector._base_path == Path("/tmp/test")
        assert connector._file_format == "json"

    def test_init_default_format(self):
        """Test filesystem connector initialization with default format."""
        config = {"base_path": "/tmp/test"}
        
        connector = FileSystemConnector(config)
        
        assert connector._file_format == "json"

    def test_init_default_base_path(self):
        """Test filesystem connector initialization with default base path."""
        config = {"format": "csv"}
        
        connector = FileSystemConnector(config)
        
        assert connector._base_path == Path(".")

    def test_validate_config_success(self):
        """Test successful config validation."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            result = connector.validate_config()
            assert result is True

    def test_validate_config_missing_path(self):
        """Test config validation with missing base path."""
        config = {}
        connector = FileSystemConnector(config)
        
        result = connector.validate_config()
        assert result is False

    def test_validate_config_nonexistent_path_parent_exists(self):
        """Test config validation with nonexistent path but parent exists."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"base_path": f"{tmp_dir}/nonexistent"}
            connector = FileSystemConnector(config)
            
            result = connector.validate_config()
            assert result is True

    @pytest.mark.asyncio
    async def test_connect_success_existing_path(self):
        """Test successful connection to existing path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            result = await connector.connect()
            
            assert result is True
            assert connector.is_connected

    @pytest.mark.asyncio
    async def test_connect_success_create_path(self):
        """Test successful connection creating missing path."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {
                "base_path": f"{tmp_dir}/new_dir",
                "create_if_missing": True
            }
            connector = FileSystemConnector(config)
            
            result = await connector.connect()
            
            assert result is True
            assert connector.is_connected
            assert Path(f"{tmp_dir}/new_dir").exists()

    @pytest.mark.asyncio
    async def test_connect_failure_missing_path_no_create(self):
        """Test connection failure with missing path and no create flag."""
        config = {"base_path": "/nonexistent/path"}
        connector = FileSystemConnector(config)
        
        result = await connector.connect()
        
        assert result is False
        assert not connector.is_connected
        assert connector.last_error is not None

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test filesystem disconnection."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            assert connector.is_connected
            
            await connector.disconnect()
            assert not connector.is_connected

    @pytest.mark.asyncio
    async def test_fetch_data_json_files(self):
        """Test fetching data from JSON files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create test JSON files
            json_data1 = {"id": 1, "name": "Test 1"}
            json_data2 = [{"id": 2, "name": "Test 2"}, {"id": 3, "name": "Test 3"}]
            
            json_file1 = Path(tmp_dir) / "test1.json"
            json_file2 = Path(tmp_dir) / "test2.json"
            
            json_file1.write_text(json.dumps(json_data1))
            json_file2.write_text(json.dumps(json_data2))
            
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            data = await connector.fetch_data("*.json")
            
            assert len(data) == 3  # 1 from file1 + 2 from file2
            assert any(item["id"] == 1 for item in data)
            assert any(item["id"] == 2 for item in data)
            assert any(item["id"] == 3 for item in data)

    @pytest.mark.asyncio
    async def test_fetch_data_csv_files(self):
        """Test fetching data from CSV files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create test CSV file
            csv_data = [
                {"id": "1", "name": "Test 1", "status": "active"},
                {"id": "2", "name": "Test 2", "status": "inactive"}
            ]
            
            csv_file = Path(tmp_dir) / "test.csv"
            with open(csv_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=["id", "name", "status"])
                writer.writeheader()
                writer.writerows(csv_data)
            
            config = {"base_path": tmp_dir, "format": "csv"}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            data = await connector.fetch_data("*.csv")
            
            assert len(data) == 2
            assert data[0]["id"] == "1"
            assert data[1]["status"] == "inactive"

    @pytest.mark.asyncio
    async def test_fetch_data_yaml_files(self):
        """Test fetching data from YAML files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create test YAML file
            yaml_data = {"items": [{"id": 1, "name": "Test"}]}
            
            yaml_file = Path(tmp_dir) / "test.yaml"
            yaml_file.write_text(yaml.dump(yaml_data))
            
            config = {"base_path": tmp_dir, "format": "yaml"}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            data = await connector.fetch_data("*.yaml")
            
            assert len(data) == 1
            assert "items" in data[0]

    @pytest.mark.asyncio
    async def test_fetch_data_txt_files(self):
        """Test fetching data from text files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create test text file
            txt_content = "Line 1\nLine 2\nLine 3\n"
            
            txt_file = Path(tmp_dir) / "test.txt"
            txt_file.write_text(txt_content)
            
            config = {"base_path": tmp_dir, "format": "txt"}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            data = await connector.fetch_data("*.txt")
            
            assert len(data) == 3  # 3 lines
            assert data[0]["line"] == "Line 1"
            assert data[0]["line_number"] == 1
            assert data[2]["line"] == "Line 3"

    @pytest.mark.asyncio
    async def test_fetch_data_recursive(self):
        """Test fetching data recursively."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create nested directory structure
            subdir = Path(tmp_dir) / "subdir"
            subdir.mkdir()
            
            json_data = {"id": 1, "name": "Nested Test"}
            json_file = subdir / "nested.json"
            json_file.write_text(json.dumps(json_data))
            
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            data = await connector.fetch_data("*.json", recursive=True)
            
            assert len(data) == 1
            assert data[0]["name"] == "Nested Test"

    @pytest.mark.asyncio
    async def test_fetch_data_not_connected(self):
        """Test fetching data when not connected."""
        config = {"base_path": "/tmp/test"}
        connector = FileSystemConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected to filesystem"):
            await connector.fetch_data("*.json")

    def test_detect_file_format_from_extension(self):
        """Test file format detection from extension."""
        config = {"base_path": "/tmp", "format": "auto"}
        connector = FileSystemConnector(config)
        
        test_cases = [
            (Path("test.json"), "json"),
            (Path("test.csv"), "csv"),
            (Path("test.yaml"), "yaml"),
            (Path("test.yml"), "yaml"),
            (Path("test.txt"), "txt"),
            (Path("test.log"), "txt"),
            (Path("test.unknown"), "txt")
        ]
        
        for file_path, expected_format in test_cases:
            result = connector._detect_file_format(file_path)
            assert result == expected_format

    def test_detect_file_format_configured(self):
        """Test file format detection with configured format."""
        config = {"base_path": "/tmp", "format": "csv"}
        connector = FileSystemConnector(config)
        
        result = connector._detect_file_format(Path("test.json"))
        assert result == "csv"  # Should use configured format

    @pytest.mark.asyncio
    async def test_write_data_json(self):
        """Test writing data to JSON file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            
            data = [
                {"id": 1, "name": "Test 1"},
                {"id": 2, "name": "Test 2"}
            ]
            
            result = await connector.write_data(data, "output.json")
            
            assert result is True
            
            # Verify file was written correctly
            output_file = Path(tmp_dir) / "output.json"
            assert output_file.exists()
            
            written_data = json.loads(output_file.read_text())
            assert len(written_data) == 2
            assert written_data[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_write_data_csv(self):
        """Test writing data to CSV file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            
            data = [
                {"id": 1, "name": "Test 1", "status": "active"},
                {"id": 2, "name": "Test 2", "status": "inactive"}
            ]
            
            result = await connector.write_data(data, "output.csv", "csv")
            
            assert result is True
            
            # Verify file was written correctly
            output_file = Path(tmp_dir) / "output.csv"
            assert output_file.exists()
            
            with open(output_file, 'r') as f:
                reader = csv.DictReader(f)
                written_data = list(reader)
                
            assert len(written_data) == 2
            assert written_data[0]["id"] == "1"

    @pytest.mark.asyncio
    async def test_write_data_yaml(self):
        """Test writing data to YAML file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            
            data = [{"id": 1, "name": "Test"}]
            
            result = await connector.write_data(data, "output.yaml", "yaml")
            
            assert result is True
            
            # Verify file was written correctly
            output_file = Path(tmp_dir) / "output.yaml"
            assert output_file.exists()
            
            written_data = yaml.safe_load(output_file.read_text())
            assert len(written_data) == 1
            assert written_data[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_write_data_empty_list(self):
        """Test writing empty data list."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            
            result = await connector.write_data([], "empty.csv", "csv")
            
            assert result is True
            
            output_file = Path(tmp_dir) / "empty.csv"
            assert output_file.exists()
            assert output_file.read_text() == ""

    @pytest.mark.asyncio
    async def test_write_data_not_connected(self):
        """Test writing data when not connected."""
        config = {"base_path": "/tmp/test"}
        connector = FileSystemConnector(config)
        
        data = [{"id": 1}]
        result = await connector.write_data(data, "test.json")
        
        assert result is False

    def test_validate_data_format_success(self):
        """Test successful data format validation."""
        config = {"base_path": "/tmp"}
        connector = FileSystemConnector(config)
        
        data = {"id": 1, "name": "Test", "content": "Some content"}
        
        result = connector.validate_data_format(data)
        assert result is True

    def test_validate_data_format_non_dict(self):
        """Test data format validation with non-dictionary."""
        config = {"base_path": "/tmp"}
        connector = FileSystemConnector(config)
        
        result = connector.validate_data_format("not a dict")
        assert result is False

    def test_validate_data_format_empty_dict(self):
        """Test data format validation with empty dictionary."""
        config = {"base_path": "/tmp"}
        connector = FileSystemConnector(config)
        
        result = connector.validate_data_format({})
        assert result is False

    @pytest.mark.asyncio
    async def test_list_files_success(self):
        """Test successful file listing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create test files
            (Path(tmp_dir) / "test1.json").write_text('{"test": 1}')
            (Path(tmp_dir) / "test2.txt").write_text("test content")
            
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            files = await connector.list_files("*")
            
            assert len(files) == 2
            
            json_file = next(f for f in files if f["name"] == "test1.json")
            assert json_file["format"] == "json"
            assert json_file["extension"] == ".json"
            assert json_file["size"] > 0
            
            txt_file = next(f for f in files if f["name"] == "test2.txt")
            assert txt_file["format"] == "txt"

    @pytest.mark.asyncio
    async def test_list_files_recursive(self):
        """Test recursive file listing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create nested structure
            subdir = Path(tmp_dir) / "subdir"
            subdir.mkdir()
            
            (Path(tmp_dir) / "top.json").write_text('{"test": 1}')
            (subdir / "nested.json").write_text('{"test": 2}')
            
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            files = await connector.list_files("*.json", recursive=True)
            
            assert len(files) == 2
            assert any("top.json" in f["name"] for f in files)
            assert any("nested.json" in f["name"] for f in files)

    @pytest.mark.asyncio
    async def test_get_file_info_success(self):
        """Test successful file info retrieval."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = Path(tmp_dir) / "test.json"
            test_file.write_text('{"test": "data"}')
            
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            file_info = await connector.get_file_info("test.json")
            
            assert file_info["name"] == "test.json"
            assert file_info["format"] == "json"
            assert file_info["extension"] == ".json"
            assert file_info["size"] > 0
            assert "modified" in file_info
            assert "created" in file_info
            assert file_info["is_readable"] is True

    @pytest.mark.asyncio
    async def test_get_file_info_not_found(self):
        """Test file info for non-existent file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            
            with pytest.raises(ConnectionError, match="Failed to get file info"):
                await connector.get_file_info("nonexistent.json")

    @pytest.mark.asyncio
    async def test_delete_file_success(self):
        """Test successful file deletion."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_file = Path(tmp_dir) / "to_delete.json"
            test_file.write_text('{"test": "data"}')
            
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            
            assert test_file.exists()
            result = await connector.delete_file("to_delete.json")
            
            assert result is True
            assert not test_file.exists()

    @pytest.mark.asyncio
    async def test_delete_file_not_found(self):
        """Test deleting non-existent file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            
            result = await connector.delete_file("nonexistent.json")
            
            assert result is False

    @pytest.mark.asyncio
    async def test_fetch_data_with_read_error(self):
        """Test fetching data with file read error."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a file with invalid JSON
            bad_file = Path(tmp_dir) / "bad.json"
            bad_file.write_text('{"invalid": json}')
            
            config = {"base_path": tmp_dir}
            connector = FileSystemConnector(config)
            
            await connector.connect()
            
            # Should handle the error gracefully and return empty list for bad file
            data = await connector.fetch_data("bad.json")
            
            assert isinstance(data, list)
            # The _read_file method should catch the error and return []

    @pytest.mark.asyncio
    async def test_list_files_not_connected(self):
        """Test listing files when not connected."""
        config = {"base_path": "/tmp/test"}
        connector = FileSystemConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected to filesystem"):
            await connector.list_files("*")

    @pytest.mark.asyncio
    async def test_get_file_info_not_connected(self):
        """Test getting file info when not connected."""
        config = {"base_path": "/tmp/test"}
        connector = FileSystemConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected to filesystem"):
            await connector.get_file_info("test.json")

    @pytest.mark.asyncio
    async def test_delete_file_not_connected(self):
        """Test deleting file when not connected."""
        config = {"base_path": "/tmp/test"}
        connector = FileSystemConnector(config)
        
        with pytest.raises(ConnectionError, match="Not connected to filesystem"):
            await connector.delete_file("test.json")
