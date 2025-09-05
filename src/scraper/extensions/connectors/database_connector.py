"""
Database connector for data sources.
"""

import asyncio
from typing import Any, Dict, List, Optional, Union
import asyncpg
import aiomysql
import aiosqlite
from .base import BaseConnector, ConnectionError, DataFormatError, AuthenticationError


class DatabaseConnector(BaseConnector):
    """
    Database connector supporting multiple database types.
    """

    def __init__(self, config: Dict[str, Any], auth_config: Optional[Dict[str, Any]] = None):
        """
        Initialize database connector.
        
        Args:
            config: Database configuration containing connection details
            auth_config: Authentication configuration (usually included in config)
        """
        super().__init__(config, auth_config)
        self._connection = None
        self.db_type = config.get('type', 'postgresql').lower()

    def validate_config(self) -> bool:
        """Validate database connector configuration."""
        required_fields = ['type']
        
        for field in required_fields:
            if field not in self.config:
                return False
        
        db_type = self.config['type'].lower()
        
        if db_type == 'postgresql':
            required_fields.extend(['host', 'database'])
        elif db_type == 'mysql':
            required_fields.extend(['host', 'database'])
        elif db_type == 'sqlite':
            required_fields.extend(['database'])  # database is the file path
        else:
            return False
            
        for field in required_fields:
            if field not in self.config:
                return False
                
        return True

    async def connect(self) -> bool:
        """Establish database connection."""
        try:
            if self._connection and not self._connection.is_closed:
                self._connected = True
                return True
                
            if self.db_type == 'postgresql':
                self._connection = await self._connect_postgresql()
            elif self.db_type == 'mysql':
                self._connection = await self._connect_mysql()
            elif self.db_type == 'sqlite':
                self._connection = await self._connect_sqlite()
            else:
                raise ConnectionError(f"Unsupported database type: {self.db_type}")
            
            if self._connection:
                self._connected = True
                return True
                
            return False
                    
        except Exception as e:
            self._last_error = ConnectionError(f"Failed to connect to database: {e}")
            return False

    async def _connect_postgresql(self):
        """Connect to PostgreSQL database."""
        connection_params = {
            'host': self.config['host'],
            'port': self.config.get('port', 5432),
            'user': self.config.get('user', self.auth_config.get('username')),
            'password': self.config.get('password', self.auth_config.get('password')),
            'database': self.config['database'],
        }
        
        # Remove None values
        connection_params = {k: v for k, v in connection_params.items() if v is not None}
        
        return await asyncpg.connect(**connection_params)

    async def _connect_mysql(self):
        """Connect to MySQL database."""
        connection_params = {
            'host': self.config['host'],
            'port': self.config.get('port', 3306),
            'user': self.config.get('user', self.auth_config.get('username')),
            'password': self.config.get('password', self.auth_config.get('password')),
            'db': self.config['database'],
        }
        
        # Remove None values
        connection_params = {k: v for k, v in connection_params.items() if v is not None}
        
        return await aiomysql.connect(**connection_params)

    async def _connect_sqlite(self):
        """Connect to SQLite database."""
        return await aiosqlite.connect(self.config['database'])

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._connection:
            if hasattr(self._connection, 'close'):
                if asyncio.iscoroutinefunction(self._connection.close):
                    await self._connection.close()
                else:
                    self._connection.close()
        self._connected = False

    async def fetch_data(self, query: str, parameters: Optional[Union[List, Dict]] = None, **kwargs) -> List[Dict[str, Any]]:
        """
        Fetch data using SQL query.
        
        Args:
            query: SQL query string
            parameters: Query parameters
            
        Returns:
            List of record dictionaries
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            if self.db_type == 'postgresql':
                return await self._fetch_postgresql(query, parameters)
            elif self.db_type == 'mysql':
                return await self._fetch_mysql(query, parameters)
            elif self.db_type == 'sqlite':
                return await self._fetch_sqlite(query, parameters)
            else:
                raise ConnectionError(f"Unsupported database type: {self.db_type}")
                
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to fetch database data: {e}")

    async def _fetch_postgresql(self, query: str, parameters: Optional[Union[List, Dict]] = None):
        """Fetch data from PostgreSQL."""
        if parameters:
            rows = await self._connection.fetch(query, *parameters if isinstance(parameters, list) else parameters)
        else:
            rows = await self._connection.fetch(query)
            
        return [dict(row) for row in rows]

    async def _fetch_mysql(self, query: str, parameters: Optional[Union[List, Dict]] = None):
        """Fetch data from MySQL."""
        async with self._connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(query, parameters)
            rows = await cursor.fetchall()
            return rows

    async def _fetch_sqlite(self, query: str, parameters: Optional[Union[List, Dict]] = None):
        """Fetch data from SQLite."""
        self._connection.row_factory = aiosqlite.Row
        async with self._connection.execute(query, parameters or []) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def execute_query(self, query: str, parameters: Optional[Union[List, Dict]] = None) -> int:
        """
        Execute a non-SELECT query (INSERT, UPDATE, DELETE).
        
        Args:
            query: SQL query string
            parameters: Query parameters
            
        Returns:
            Number of affected rows
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            if self.db_type == 'postgresql':
                result = await self._connection.execute(query, *(parameters or []))
                # Extract number from "INSERT 0 5" format
                return int(result.split()[-1]) if result else 0
                
            elif self.db_type == 'mysql':
                async with self._connection.cursor() as cursor:
                    await cursor.execute(query, parameters)
                    await self._connection.commit()
                    return cursor.rowcount
                    
            elif self.db_type == 'sqlite':
                await self._connection.execute(query, parameters or [])
                await self._connection.commit()
                return self._connection.total_changes
                
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to execute query: {e}")

    def validate_data_format(self, data: Any) -> bool:
        """
        Validate database record data format.
        
        Args:
            data: Database record data to validate
            
        Returns:
            True if data format is valid
        """
        if not isinstance(data, dict):
            return False
            
        # All values should be JSON serializable
        try:
            import json
            json.dumps(data, default=str)  # default=str handles dates, etc.
            return True
        except (TypeError, ValueError):
            return False

    async def test_query(self, query: str = "SELECT 1") -> bool:
        """
        Test database connection with a simple query.
        
        Args:
            query: Test query to execute
            
        Returns:
            True if query executes successfully
        """
        try:
            await self.fetch_data(query)
            return True
        except Exception:
            return False

    async def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """
        Get information about a database table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dictionary containing table information
        """
        if not self.is_connected:
            raise ConnectionError("Not connected to database")

        try:
            if self.db_type == 'postgresql':
                query = """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns 
                    WHERE table_name = $1
                    ORDER BY ordinal_position
                """
                columns = await self.fetch_data(query, [table_name])
                
            elif self.db_type == 'mysql':
                query = """
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns 
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """
                columns = await self.fetch_data(query, [table_name])
                
            elif self.db_type == 'sqlite':
                query = f"PRAGMA table_info({table_name})"
                pragma_info = await self.fetch_data(query)
                columns = [
                    {
                        'column_name': row['name'],
                        'data_type': row['type'],
                        'is_nullable': 'YES' if not row['notnull'] else 'NO',
                        'column_default': row['dflt_value']
                    }
                    for row in pragma_info
                ]
                
            return {
                'table_name': table_name,
                'columns': columns,
                'column_count': len(columns)
            }
            
        except Exception as e:
            self._last_error = e
            raise ConnectionError(f"Failed to get table info: {e}")
