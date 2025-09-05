"""
File system connector for data sources.
"""

import asyncio
import aiofiles
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import json
import csv
import yaml
from .base import BaseConnector, ConnectionError, DataFormatError


class FileSystemConnector(BaseConnector):
    """
    File system connector for reading data from local or network file systems.
    """

    def __init__(self, config: Dict[str, Any], auth_config: Optional[Dict[str, Any]] = None):
        """
        Initialize filesystem connector.
        
        Args:
            config: Filesystem configuration containing path and format info
            auth_config: Authentication configuration (if needed for network paths)
        """
        super().__init__(config, auth_config)
        self._base_path = Path(config.get('base_path', '.'))
        self._file_format = config.get('format', 'json').lower()

    def validate_config(self) -> bool:
        """Validate filesystem connector configuration."""
        required_fields = ['base_path']
        
        for field in required_fields:
            if field not in self.config:
                return False
        
        # Check if path is accessible
        try:
            path = Path(self.config['base_path'])
            return path.exists() or path.parent.exists()
        except Exception:
            return False

    async def connect(self) -> bool:
        """Establish connection to filesystem."""
        try:
            # Check if base path exists and is accessible
            if not self._base_path.exists():
                if self.config.get('create_if_missing', False):
                    self._base_path.mkdir(parents=True, exist_ok=True)
                else:
                    raise ConnectionError(f"Base path does not exist: {self._base_path}")
            
            # Test read access
            if not os.access(self._base_path, os.R_OK):
                raise ConnectionError(f"No read access to base path: {self._base_path}")
            
            self._connected = True
            return True
                    
        except Exception as e:
            self._last_error = ConnectionError(f"Failed to connect to filesystem: {e}")
            return False

    async def disconnect(self) -> None:
        """Close filesystem connection."""
        # No persistent connection to close for filesystem
        self._connected = False

    async def fetch_data(self, file_pattern: str = "*", recursive: bool = False, **kwargs) -> List[Dict[str, Any]]:
        """
        Fetch data from files matching pattern.
        
        Args:
            file_pattern: File pattern to match (glob style)
            recursive: Search recursively in subdirectories
            
        Returns:
            List of data records from files
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to filesystem")

        try:
            files = []
            if recursive:
                files = list(self._base_path.rglob(file_pattern))
            else:
                files = list(self._base_path.glob(file_pattern))
            
            all_data = []
            for file_path in files:
                if file_path.is_file():
                    file_data = await self._read_file(file_path)
                    if file_data:
                        all_data.extend(file_data)
            
            return all_data
                    
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to fetch filesystem data: {e}")

    async def _read_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Read data from a single file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            List of data records from the file
        """
        try:
            file_format = self._detect_file_format(file_path)
            
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            if file_format == 'json':
                data = json.loads(content)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return [data]
                else:
                    return [{'data': data}]
                    
            elif file_format == 'csv':
                # Use synchronous csv reader with StringIO for async compatibility
                import io
                csv_data = []
                csv_reader = csv.DictReader(io.StringIO(content))
                for row in csv_reader:
                    csv_data.append(dict(row))
                return csv_data
                
            elif file_format == 'yaml':
                data = yaml.safe_load(content)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return [data]
                else:
                    return [{'data': data}]
                    
            elif file_format == 'txt':
                # Return each line as a record
                lines = content.strip().split('\n')
                return [{'line': line.strip(), 'line_number': i+1, 'file': str(file_path)} 
                       for i, line in enumerate(lines) if line.strip()]
                       
            else:
                # Unknown format - return raw content
                return [{'content': content, 'file': str(file_path), 'format': file_format}]
                
        except Exception as e:
            self.logger.error(f"Error reading file {file_path}: {e}")
            return []

    def _detect_file_format(self, file_path: Path) -> str:
        """
        Detect file format from extension.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Detected file format
        """
        # Use configured format if specified
        if self._file_format != 'auto':
            return self._file_format
            
        # Auto-detect from extension
        extension = file_path.suffix.lower()
        format_mapping = {
            '.json': 'json',
            '.csv': 'csv',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.txt': 'txt',
            '.log': 'txt',
        }
        
        return format_mapping.get(extension, 'txt')

    async def write_data(self, data: List[Dict[str, Any]], filename: str, 
                        file_format: Optional[str] = None) -> bool:
        """
        Write data to a file.
        
        Args:
            data: Data to write
            filename: Name of the file
            file_format: Format to write (defaults to configured format)
            
        Returns:
            True if write successful
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to filesystem")

        try:
            file_path = self._base_path / filename
            format_to_use = file_format or self._file_format
            
            if format_to_use == 'json':
                content = json.dumps(data, indent=2, default=str)
            elif format_to_use == 'csv':
                if not data:
                    content = ""
                else:
                    import io
                    output = io.StringIO()
                    fieldnames = data[0].keys()
                    writer = csv.DictWriter(output, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(data)
                    content = output.getvalue()
            elif format_to_use == 'yaml':
                content = yaml.dump(data, default_flow_style=False)
            else:
                # Default to JSON
                content = json.dumps(data, indent=2, default=str)
            
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            
            return True
            
        except Exception as e:
            self._last_error = e
            return False

    def validate_data_format(self, data: Any) -> bool:
        """
        Validate file data format.
        
        Args:
            data: File data to validate
            
        Returns:
            True if data format is valid
        """
        if not isinstance(data, dict):
            return False
        
        # Should contain at least some content
        return len(data) > 0

    async def list_files(self, pattern: str = "*", recursive: bool = False) -> List[Dict[str, Any]]:
        """
        List files matching pattern with metadata.
        
        Args:
            pattern: File pattern to match
            recursive: Search recursively
            
        Returns:
            List of file metadata dictionaries
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to filesystem")

        try:
            files = []
            if recursive:
                file_paths = list(self._base_path.rglob(pattern))
            else:
                file_paths = list(self._base_path.glob(pattern))
            
            for file_path in file_paths:
                if file_path.is_file():
                    stat = file_path.stat()
                    files.append({
                        'name': file_path.name,
                        'path': str(file_path),
                        'size': stat.st_size,
                        'modified': stat.st_mtime,
                        'format': self._detect_file_format(file_path),
                        'extension': file_path.suffix,
                    })
            
            return files
            
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to list files: {e}")

    async def get_file_info(self, filename: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific file.
        
        Args:
            filename: Name of the file
            
        Returns:
            Dictionary containing file information
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to filesystem")

        try:
            file_path = self._base_path / filename
            
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {filename}")
            
            stat = file_path.stat()
            
            return {
                'name': file_path.name,
                'path': str(file_path),
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'created': stat.st_ctime,
                'format': self._detect_file_format(file_path),
                'extension': file_path.suffix,
                'is_readable': os.access(file_path, os.R_OK),
                'is_writable': os.access(file_path, os.W_OK),
            }
            
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to get file info: {e}")

    async def delete_file(self, filename: str) -> bool:
        """
        Delete a file.
        
        Args:
            filename: Name of the file to delete
            
        Returns:
            True if deletion successful
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to filesystem")

        try:
            file_path = self._base_path / filename
            
            if file_path.exists():
                file_path.unlink()
                return True
            else:
                return False
                
        except Exception as e:
            self._last_error = e
            return False
