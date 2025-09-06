"""
Comprehensive test suite for API Key Management System - Issue #476.

Tests all authentication requirements for APIKeyManager:
- API key generation with proper entropy and uniqueness
- Key validation and expiration handling  
- Key rotation and revocation mechanisms
- Rate limiting per API key
- DynamoDB storage and retrieval operations
- Security and performance under load
"""

import asyncio
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

from src.api.auth.api_key_manager import (
    APIKey,
    APIKeyGenerator,
    APIKeyManager,
    APIKeyStatus,
    DynamoDBAPIKeyStore,
)


class TestAPIKeyGenerator:
    """Test secure API key generation utilities."""

    def test_generate_api_key_format(self):
        """Test API key generation format and uniqueness."""
        key1 = APIKeyGenerator.generate_api_key()
        key2 = APIKeyGenerator.generate_api_key()
        
        # Keys should be unique
        assert key1 != key2
        
        # Keys should have proper format
        assert key1.startswith("nn_")
        assert key2.startswith("nn_")
        
        # Keys should have sufficient length (prefix + 43 chars base64url)
        assert len(key1) >= 46  # "nn_" + 43 chars
        assert len(key2) >= 46

    def test_generate_api_key_entropy(self):
        """Test API key entropy and randomness."""
        keys = [APIKeyGenerator.generate_api_key() for _ in range(100)]
        
        # All keys should be unique
        assert len(set(keys)) == 100
        
        # Keys should contain only valid URL-safe base64 characters
        for key in keys[:10]:  # Test first 10 for performance
            key_part = key[3:]  # Remove "nn_" prefix
            # Should only contain valid base64url chars: A-Z, a-z, 0-9, -, _
            assert all(c.isalnum() or c in '-_' for c in key_part)

    def test_generate_key_id_format(self):
        """Test key ID generation format and uniqueness."""
        id1 = APIKeyGenerator.generate_key_id()
        id2 = APIKeyGenerator.generate_key_id()
        
        # IDs should be unique
        assert id1 != id2
        
        # IDs should have proper format
        assert id1.startswith("key_")
        assert id2.startswith("key_")
        
        # IDs should have proper length (prefix + 32 hex chars)
        assert len(id1) == 36  # "key_" + 32 chars
        assert len(id2) == 36

    def test_hash_api_key_consistency(self):
        """Test API key hashing consistency and security."""
        api_key = "nn_test_key_12345"
        
        # Same key should produce same hash
        hash1 = APIKeyGenerator.hash_api_key(api_key)
        hash2 = APIKeyGenerator.hash_api_key(api_key)
        assert hash1 == hash2
        
        # Hash should be hex string
        assert all(c in '0123456789abcdef' for c in hash1.lower())
        
        # Hash should have sufficient length (SHA256 = 64 hex chars)
        assert len(hash1) == 64

    def test_hash_api_key_different_keys(self):
        """Test different keys produce different hashes."""
        key1 = "nn_test_key_1"
        key2 = "nn_test_key_2"
        
        hash1 = APIKeyGenerator.hash_api_key(key1)
        hash2 = APIKeyGenerator.hash_api_key(key2)
        
        assert hash1 != hash2

    @patch.dict(os.environ, {'API_KEY_SALT': 'custom_salt_value'})
    def test_hash_api_key_with_custom_salt(self):
        """Test API key hashing with custom salt."""
        api_key = "nn_test_key"
        
        hash_with_custom_salt = APIKeyGenerator.hash_api_key(api_key)
        
        # Should still produce valid hash
        assert len(hash_with_custom_salt) == 64
        assert all(c in '0123456789abcdef' for c in hash_with_custom_salt.lower())

    def test_verify_api_key_valid(self):
        """Test API key verification for valid keys."""
        api_key = "nn_test_verification_key"
        key_hash = APIKeyGenerator.hash_api_key(api_key)
        
        # Valid key should verify successfully
        assert APIKeyGenerator.verify_api_key(api_key, key_hash) is True

    def test_verify_api_key_invalid(self):
        """Test API key verification for invalid keys."""
        api_key = "nn_test_verification_key"
        wrong_key = "nn_wrong_key"
        key_hash = APIKeyGenerator.hash_api_key(api_key)
        
        # Wrong key should fail verification
        assert APIKeyGenerator.verify_api_key(wrong_key, key_hash) is False

    def test_verify_api_key_timing_attack_protection(self):
        """Test that verification uses timing-safe comparison."""
        api_key = "nn_test_timing_key"
        key_hash = APIKeyGenerator.hash_api_key(api_key)
        
        # Patch hmac.compare_digest to ensure it's being called
        with patch('hmac.compare_digest', return_value=True) as mock_compare:
            APIKeyGenerator.verify_api_key(api_key, key_hash)
            mock_compare.assert_called_once()


class TestAPIKey:
    """Test APIKey data class operations."""

    def test_api_key_creation(self):
        """Test APIKey creation with all parameters."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)
        
        api_key = APIKey(
            key_id="key_123",
            user_id="user_456",
            key_prefix="nn_abcd",
            key_hash="hash_value",
            name="Test Key",
            status=APIKeyStatus.ACTIVE,
            created_at=now,
            expires_at=expires,
            last_used_at=None,
            usage_count=0,
            permissions=["read:articles"],
            rate_limit=100
        )
        
        assert api_key.key_id == "key_123"
        assert api_key.user_id == "user_456"
        assert api_key.status == APIKeyStatus.ACTIVE
        assert api_key.permissions == ["read:articles"]
        assert api_key.rate_limit == 100

    def test_api_key_to_dict(self):
        """Test APIKey dictionary conversion."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=30)
        
        api_key = APIKey(
            key_id="key_123",
            user_id="user_456",
            key_prefix="nn_abcd",
            key_hash="hash_value",
            name="Test Key",
            status=APIKeyStatus.ACTIVE,
            created_at=now,
            expires_at=expires,
            last_used_at=now,
            usage_count=5,
            permissions=["read:articles"],
            rate_limit=100
        )
        
        data = api_key.to_dict()
        
        assert data["key_id"] == "key_123"
        assert data["status"] == "active"
        assert data["usage_count"] == 5
        assert data["permissions"] == ["read:articles"]
        assert data["created_at"] == now.isoformat()
        assert data["expires_at"] == expires.isoformat()

    def test_api_key_from_dict(self):
        """Test APIKey creation from dictionary."""
        now = datetime.now(timezone.utc)
        data = {
            "key_id": "key_123",
            "user_id": "user_456",
            "key_prefix": "nn_abcd",
            "key_hash": "hash_value",
            "name": "Test Key",
            "status": "active",
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(days=30)).isoformat(),
            "last_used_at": now.isoformat(),
            "usage_count": 10,
            "permissions": ["read:articles"],
            "rate_limit": 50
        }
        
        api_key = APIKey.from_dict(data)
        
        assert api_key.key_id == "key_123"
        assert api_key.status == APIKeyStatus.ACTIVE
        assert api_key.usage_count == 10
        assert api_key.permissions == ["read:articles"]
        assert api_key.rate_limit == 50

    def test_api_key_from_dict_optional_fields(self):
        """Test APIKey creation with optional fields missing."""
        now = datetime.now(timezone.utc)
        data = {
            "key_id": "key_123",
            "user_id": "user_456", 
            "key_prefix": "nn_abcd",
            "key_hash": "hash_value",
            "name": "Test Key",
            "status": "active",
            "created_at": now.isoformat()
            # Missing optional fields
        }
        
        api_key = APIKey.from_dict(data)
        
        assert api_key.expires_at is None
        assert api_key.last_used_at is None
        assert api_key.usage_count == 0
        assert api_key.permissions is None
        assert api_key.rate_limit is None


class TestDynamoDBAPIKeyStore:
    """Test DynamoDB storage operations."""

    @pytest.fixture
    def mock_dynamodb_store(self):
        """Create mock DynamoDB store for testing."""
        with patch('src.api.auth.api_key_manager.BOTO3_AVAILABLE', True), \
             patch('boto3.resource') as mock_resource:
            
            mock_table = MagicMock()
            mock_resource.return_value.Table.return_value = mock_table
            
            store = DynamoDBAPIKeyStore()
            store.table = mock_table
            return store, mock_table

    @pytest.mark.asyncio
    async def test_store_api_key_success(self, mock_dynamodb_store):
        """Test successful API key storage."""
        store, mock_table = mock_dynamodb_store
        
        api_key = APIKey(
            key_id="key_123",
            user_id="user_456",
            key_prefix="nn_abcd",
            key_hash="hash_value",
            name="Test Key",
            status=APIKeyStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            usage_count=0
        )
        
        mock_table.put_item.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
        
        result = await store.store_api_key(api_key)
        
        assert result is True
        mock_table.put_item.assert_called_once()
        call_args = mock_table.put_item.call_args[1]
        assert call_args["Item"]["key_id"] == "key_123"

    @pytest.mark.asyncio
    async def test_store_api_key_failure(self, mock_dynamodb_store):
        """Test API key storage failure handling."""
        store, mock_table = mock_dynamodb_store
        
        api_key = APIKey(
            key_id="key_123",
            user_id="user_456",
            key_prefix="nn_abcd",
            key_hash="hash_value",
            name="Test Key",
            status=APIKeyStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            usage_count=0
        )
        
        mock_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ValidationException"}}, "PutItem"
        )
        
        result = await store.store_api_key(api_key)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_api_key_success(self, mock_dynamodb_store):
        """Test successful API key retrieval."""
        store, mock_table = mock_dynamodb_store
        
        mock_item_data = {
            "key_id": "key_123",
            "user_id": "user_456",
            "key_prefix": "nn_abcd",
            "key_hash": "hash_value",
            "name": "Test Key",
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "usage_count": 5
        }
        
        mock_table.get_item.return_value = {"Item": mock_item_data}
        
        result = await store.get_api_key("key_123")
        
        assert result is not None
        assert result.key_id == "key_123"
        assert result.status == APIKeyStatus.ACTIVE
        assert result.usage_count == 5

    @pytest.mark.asyncio
    async def test_get_api_key_not_found(self, mock_dynamodb_store):
        """Test API key retrieval when key doesn't exist."""
        store, mock_table = mock_dynamodb_store
        
        mock_table.get_item.return_value = {}  # No Item in response
        
        result = await store.get_api_key("nonexistent_key")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_api_keys_success(self, mock_dynamodb_store):
        """Test successful retrieval of user's API keys."""
        store, mock_table = mock_dynamodb_store
        
        mock_items = [
            {
                "key_id": "key_1",
                "user_id": "user_456",
                "key_prefix": "nn_abc1",
                "key_hash": "hash1",
                "name": "Key 1",
                "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "usage_count": 10
            },
            {
                "key_id": "key_2",
                "user_id": "user_456",
                "key_prefix": "nn_abc2",
                "key_hash": "hash2",
                "name": "Key 2",
                "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "usage_count": 5
            }
        ]
        
        mock_table.query.return_value = {"Items": mock_items}
        
        result = await store.get_user_api_keys("user_456")
        
        assert len(result) == 2
        assert result[0].key_id == "key_1"
        assert result[1].key_id == "key_2"
        assert all(key.user_id == "user_456" for key in result)

    @pytest.mark.asyncio
    async def test_update_api_key_usage_success(self, mock_dynamodb_store):
        """Test successful API key usage update."""
        store, mock_table = mock_dynamodb_store
        
        mock_table.update_item.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
        
        result = await store.update_api_key_usage("key_123")
        
        assert result is True
        mock_table.update_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_api_key_success(self, mock_dynamodb_store):
        """Test successful API key revocation."""
        store, mock_table = mock_dynamodb_store
        
        mock_table.update_item.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
        
        result = await store.revoke_api_key("key_123")
        
        assert result is True
        mock_table.update_item.assert_called_once()
        
        # Verify the status is set to revoked
        call_args = mock_table.update_item.call_args[1]
        assert call_args["ExpressionAttributeValues"][":status"] == "revoked"

    @pytest.mark.asyncio
    async def test_delete_api_key_success(self, mock_dynamodb_store):
        """Test successful API key deletion."""
        store, mock_table = mock_dynamodb_store
        
        mock_table.delete_item.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
        
        result = await store.delete_api_key("key_123")
        
        assert result is True
        mock_table.delete_item.assert_called_once_with(Key={"key_id": "key_123"})

    @pytest.mark.asyncio 
    async def test_no_dynamodb_fallback(self):
        """Test behavior when DynamoDB is not available."""
        with patch('src.api.auth.api_key_manager.BOTO3_AVAILABLE', False):
            store = DynamoDBAPIKeyStore()
            
            api_key = APIKey(
                key_id="key_123",
                user_id="user_456",
                key_prefix="nn_abcd",
                key_hash="hash_value",
                name="Test Key",
                status=APIKeyStatus.ACTIVE,
                created_at=datetime.now(timezone.utc),
                usage_count=0
            )
            
            # Operations should return False/None when DynamoDB unavailable
            assert await store.store_api_key(api_key) is False
            assert await store.get_api_key("key_123") is None
            assert await store.get_user_api_keys("user_456") == []
            assert await store.update_api_key_usage("key_123") is False
            assert await store.revoke_api_key("key_123") is False
            assert await store.delete_api_key("key_123") is False


class TestAPIKeyManager:
    """Test high-level API key management operations."""

    @pytest.fixture
    def api_key_manager(self):
        """Create APIKeyManager with mocked store."""
        with patch('src.api.auth.api_key_manager.DynamoDBAPIKeyStore') as mock_store_class:
            mock_store = MagicMock()
            mock_store_class.return_value = mock_store
            
            manager = APIKeyManager()
            manager.store = mock_store
            return manager, mock_store

    @pytest.mark.asyncio
    async def test_create_api_key_success(self, api_key_manager):
        """Test successful API key creation."""
        manager, mock_store = api_key_manager
        
        mock_store.store_api_key.return_value = True
        
        result = await manager.create_api_key(
            user_id="user_123",
            name="Test API Key",
            permissions=["read:articles"],
            expires_days=30,
            rate_limit=100
        )
        
        assert result is not None
        assert result["key_id"].startswith("key_")
        assert result["api_key"].startswith("nn_")
        assert result["name"] == "Test API Key"
        assert result["permissions"] == ["read:articles"]
        assert result["rate_limit"] == 100
        
        mock_store.store_api_key.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_api_key_storage_failure(self, api_key_manager):
        """Test API key creation with storage failure."""
        manager, mock_store = api_key_manager
        
        mock_store.store_api_key.return_value = False
        
        result = await manager.create_api_key(
            user_id="user_123",
            name="Test API Key"
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_api_key_success(self, api_key_manager):
        """Test successful API key validation."""
        manager, mock_store = api_key_manager
        
        # Create a test key
        api_key_value = "nn_test_key_123"
        api_key_hash = APIKeyGenerator.hash_api_key(api_key_value)
        
        mock_api_key = APIKey(
            key_id="key_123",
            user_id="user_456",
            key_prefix=api_key_value[:8],
            key_hash=api_key_hash,
            name="Test Key",
            status=APIKeyStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            usage_count=0
        )
        
        # Mock finding key by prefix
        mock_store.get_user_api_keys.return_value = [mock_api_key]
        mock_store.update_api_key_usage.return_value = True
        
        result = await manager.validate_api_key(api_key_value)
        
        assert result is not None
        assert result.key_id == "key_123"
        mock_store.update_api_key_usage.assert_called_once_with("key_123")

    @pytest.mark.asyncio
    async def test_validate_api_key_invalid(self, api_key_manager):
        """Test validation of invalid API key."""
        manager, mock_store = api_key_manager
        
        mock_store.get_user_api_keys.return_value = []
        
        result = await manager.validate_api_key("nn_invalid_key")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_api_key_expired(self, api_key_manager):
        """Test validation of expired API key."""
        manager, mock_store = api_key_manager
        
        api_key_value = "nn_test_key_123"
        api_key_hash = APIKeyGenerator.hash_api_key(api_key_value)
        
        # Create expired key
        expired_key = APIKey(
            key_id="key_123",
            user_id="user_456",
            key_prefix=api_key_value[:8],
            key_hash=api_key_hash,
            name="Expired Key",
            status=APIKeyStatus.ACTIVE,
            created_at=datetime.now(timezone.utc) - timedelta(days=60),
            expires_at=datetime.now(timezone.utc) - timedelta(days=30),  # Expired
            usage_count=0
        )
        
        mock_store.get_user_api_keys.return_value = [expired_key]
        
        result = await manager.validate_api_key(api_key_value)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_api_key_revoked(self, api_key_manager):
        """Test validation of revoked API key."""
        manager, mock_store = api_key_manager
        
        api_key_value = "nn_test_key_123"
        api_key_hash = APIKeyGenerator.hash_api_key(api_key_value)
        
        # Create revoked key
        revoked_key = APIKey(
            key_id="key_123",
            user_id="user_456",
            key_prefix=api_key_value[:8],
            key_hash=api_key_hash,
            name="Revoked Key",
            status=APIKeyStatus.REVOKED,
            created_at=datetime.now(timezone.utc),
            usage_count=0
        )
        
        mock_store.get_user_api_keys.return_value = [revoked_key]
        
        result = await manager.validate_api_key(api_key_value)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_rotate_api_key_success(self, api_key_manager):
        """Test successful API key rotation."""
        manager, mock_store = api_key_manager
        
        # Mock existing key
        old_key = APIKey(
            key_id="key_123",
            user_id="user_456",
            key_prefix="nn_old",
            key_hash="old_hash",
            name="Old Key",
            status=APIKeyStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
            usage_count=100,
            permissions=["read:articles"],
            rate_limit=50
        )
        
        mock_store.get_api_key.return_value = old_key
        mock_store.revoke_api_key.return_value = True
        mock_store.store_api_key.return_value = True
        
        result = await manager.rotate_api_key("key_123")
        
        assert result is not None
        assert result["api_key"].startswith("nn_")
        assert result["name"] == "Old Key"
        assert result["permissions"] == ["read:articles"]
        assert result["rate_limit"] == 50
        
        # Verify old key was revoked and new key was stored
        mock_store.revoke_api_key.assert_called_once_with("key_123")
        mock_store.store_api_key.assert_called_once()


class TestPerformanceAndSecurity:
    """Test performance and security aspects."""

    def test_key_generation_performance(self):
        """Test API key generation performance."""
        import time
        
        start_time = time.time()
        keys = [APIKeyGenerator.generate_api_key() for _ in range(1000)]
        end_time = time.time()
        
        # Should generate 1000 keys in reasonable time (< 1 second)
        assert end_time - start_time < 1.0
        
        # All keys should be unique
        assert len(set(keys)) == 1000

    def test_hash_verification_performance(self):
        """Test hash verification performance."""
        import time
        
        api_key = "nn_performance_test_key"
        key_hash = APIKeyGenerator.hash_api_key(api_key)
        
        start_time = time.time()
        for _ in range(100):
            APIKeyGenerator.verify_api_key(api_key, key_hash)
        end_time = time.time()
        
        # 100 verifications should complete quickly (< 0.5 seconds)
        assert end_time - start_time < 0.5

    def test_concurrent_key_generation(self):
        """Test thread-safe key generation."""
        import threading
        import concurrent.futures
        
        def generate_keys(count):
            return [APIKeyGenerator.generate_api_key() for _ in range(count)]
        
        # Generate keys concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(generate_keys, 50) for _ in range(10)]
            results = []
            for future in concurrent.futures.as_completed(futures):
                results.extend(future.result())
        
        # All 500 keys should be unique
        assert len(set(results)) == 500

    def test_key_entropy_statistical_analysis(self):
        """Test statistical properties of key entropy."""
        keys = [APIKeyGenerator.generate_api_key() for _ in range(100)]
        
        # Extract the random parts (without "nn_" prefix)
        key_parts = [key[3:] for key in keys]
        
        # Test character distribution
        char_counts = {}
        for key in key_parts:
            for char in key:
                char_counts[char] = char_counts.get(char, 0) + 1
        
        # Should have reasonable character distribution (no character > 5% of total)
        total_chars = sum(char_counts.values())
        for char, count in char_counts.items():
            assert count / total_chars < 0.05, f"Character '{char}' appears too frequently"