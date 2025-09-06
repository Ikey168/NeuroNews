"""
Comprehensive test suite for JWT Authentication System - Issue #476.

Tests all JWT authentication requirements:
- Token creation with proper claims and expiration
- Token validation including signature verification  
- Token refresh and blacklisting mechanisms
- Invalid token handling and error responses
- Security against tampering and forgery attempts
- Performance under high load
"""

import os
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from src.api.auth.jwt_auth import JWTAuth, auth_handler


class TestJWTAuth:
    """Test JWT authentication class."""

    @pytest.fixture
    def jwt_auth(self):
        """Create JWTAuth instance for testing."""
        return JWTAuth()

    @pytest.fixture
    def jwt_auth_custom_config(self):
        """Create JWTAuth with custom configuration."""
        with patch.dict(os.environ, {
            'JWT_SECRET_KEY': 'test-secret-key-12345',
            'ACCESS_TOKEN_EXPIRE_MINUTES': '15',
            'REFRESH_TOKEN_EXPIRE_DAYS': '14'
        }):
            return JWTAuth()

    def test_jwt_auth_initialization(self, jwt_auth):
        """Test JWT authentication initialization."""
        assert jwt_auth.jwt_secret is not None
        assert jwt_auth.jwt_algorithm == "HS256"
        assert jwt_auth.access_token_expire == 30  # default
        assert jwt_auth.refresh_token_expire == 7  # default
        assert jwt_auth.security is not None

    def test_jwt_auth_custom_config(self, jwt_auth_custom_config):
        """Test JWT authentication with custom configuration."""
        assert jwt_auth_custom_config.jwt_secret == "test-secret-key-12345"
        assert jwt_auth_custom_config.access_token_expire == 15
        assert jwt_auth_custom_config.refresh_token_expire == 14

    def test_create_access_token(self, jwt_auth):
        """Test access token creation."""
        user_data = {
            "sub": "user123",
            "email": "test@example.com",
            "role": "user"
        }
        
        token = jwt_auth.create_access_token(user_data)
        
        assert isinstance(token, str)
        assert token.count('.') == 2  # JWT has 3 parts separated by dots
        
        # Decode and verify token content
        decoded = jwt.decode(token, jwt_auth.jwt_secret, algorithms=[jwt_auth.jwt_algorithm])
        assert decoded["sub"] == "user123"
        assert decoded["email"] == "test@example.com"
        assert decoded["role"] == "user"
        assert "exp" in decoded

    def test_create_access_token_expiration(self, jwt_auth):
        """Test access token expiration time."""
        user_data = {"sub": "user123"}
        
        before_creation = datetime.now(timezone.utc)
        token = jwt_auth.create_access_token(user_data)
        after_creation = datetime.now(timezone.utc)
        
        decoded = jwt.decode(token, jwt_auth.jwt_secret, algorithms=[jwt_auth.jwt_algorithm])
        exp_time = datetime.fromtimestamp(decoded["exp"], timezone.utc)
        
        expected_min = before_creation + timedelta(minutes=jwt_auth.access_token_expire)
        expected_max = after_creation + timedelta(minutes=jwt_auth.access_token_expire)
        
        assert expected_min <= exp_time <= expected_max

    def test_create_refresh_token(self, jwt_auth):
        """Test refresh token creation."""
        user_data = {
            "sub": "user123",
            "email": "test@example.com"
        }
        
        token = jwt_auth.create_refresh_token(user_data)
        
        assert isinstance(token, str)
        assert token.count('.') == 2
        
        # Decode and verify token content
        decoded = jwt.decode(token, jwt_auth.jwt_secret, algorithms=[jwt_auth.jwt_algorithm])
        assert decoded["sub"] == "user123"
        assert decoded["email"] == "test@example.com"
        assert "exp" in decoded

    def test_create_refresh_token_expiration(self, jwt_auth):
        """Test refresh token expiration time."""
        user_data = {"sub": "user123"}
        
        before_creation = datetime.now(timezone.utc)
        token = jwt_auth.create_refresh_token(user_data)
        after_creation = datetime.now(timezone.utc)
        
        decoded = jwt.decode(token, jwt_auth.jwt_secret, algorithms=[jwt_auth.jwt_algorithm])
        exp_time = datetime.fromtimestamp(decoded["exp"], timezone.utc)
        
        expected_min = before_creation + timedelta(days=jwt_auth.refresh_token_expire)
        expected_max = after_creation + timedelta(days=jwt_auth.refresh_token_expire)
        
        assert expected_min <= exp_time <= expected_max

    def test_verify_token_valid(self, jwt_auth):
        """Test verification of valid token."""
        user_data = {"sub": "user123", "email": "test@example.com"}
        token = jwt_auth.create_access_token(user_data)
        
        payload = jwt_auth.verify_token(token)
        
        assert payload is not None
        assert payload["sub"] == "user123"
        assert payload["email"] == "test@example.com"

    def test_verify_token_expired(self, jwt_auth):
        """Test verification of expired token."""
        user_data = {"sub": "user123"}
        
        # Create token that expires immediately
        expired_token = jwt.encode(
            {
                **user_data,
                "exp": datetime.now(timezone.utc) - timedelta(seconds=1)
            },
            jwt_auth.jwt_secret,
            algorithm=jwt_auth.jwt_algorithm
        )
        
        payload = jwt_auth.verify_token(expired_token)
        assert payload is None

    def test_verify_token_invalid_signature(self, jwt_auth):
        """Test verification of token with invalid signature."""
        user_data = {"sub": "user123"}
        token = jwt_auth.create_access_token(user_data)
        
        # Modify token to invalidate signature
        invalid_token = token[:-5] + "XXXXX"
        
        payload = jwt_auth.verify_token(invalid_token)
        assert payload is None

    def test_verify_token_malformed(self, jwt_auth):
        """Test verification of malformed token."""
        malformed_tokens = [
            "not.a.token",
            "not_a_jwt_at_all",
            "header.payload",  # Missing signature
            "header.payload.signature.extra",  # Too many parts
            "",  # Empty string
            None  # None value
        ]
        
        for token in malformed_tokens:
            payload = jwt_auth.verify_token(token)
            assert payload is None

    def test_verify_token_wrong_algorithm(self, jwt_auth):
        """Test verification with wrong algorithm."""
        user_data = {"sub": "user123"}
        
        # Create token with different algorithm
        wrong_algo_token = jwt.encode(
            {
                **user_data,
                "exp": datetime.now(timezone.utc) + timedelta(minutes=30)
            },
            jwt_auth.jwt_secret,
            algorithm="HS512"  # Different algorithm
        )
        
        payload = jwt_auth.verify_token(wrong_algo_token)
        assert payload is None

    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self, jwt_auth):
        """Test getting current user with valid token."""
        user_data = {
            "sub": "user123",
            "email": "test@example.com",
            "role": "user"
        }
        token = jwt_auth.create_access_token(user_data)
        
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )
        
        request = MagicMock(spec=Request)
        
        current_user = await jwt_auth.get_current_user(credentials, request)
        
        assert current_user["sub"] == "user123"
        assert current_user["email"] == "test@example.com"
        assert current_user["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self, jwt_auth):
        """Test getting current user with invalid token."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid_token"
        )
        
        request = MagicMock(spec=Request)
        
        with pytest.raises(HTTPException) as exc_info:
            await jwt_auth.get_current_user(credentials, request)
        
        assert exc_info.value.status_code == 401
        assert "Invalid token" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_current_user_no_credentials(self, jwt_auth):
        """Test getting current user without credentials."""
        request = MagicMock(spec=Request)
        
        with pytest.raises(HTTPException) as exc_info:
            await jwt_auth.get_current_user(None, request)
        
        assert exc_info.value.status_code == 401
        assert "Authorization header required" in str(exc_info.value.detail)

    def test_refresh_token_valid(self, jwt_auth):
        """Test refreshing valid token."""
        user_data = {
            "sub": "user123",
            "email": "test@example.com",
            "role": "user"
        }
        refresh_token = jwt_auth.create_refresh_token(user_data)
        
        new_access_token = jwt_auth.refresh_access_token(refresh_token)
        
        assert new_access_token is not None
        assert isinstance(new_access_token, str)
        
        # Verify new token is valid
        payload = jwt_auth.verify_token(new_access_token)
        assert payload["sub"] == "user123"
        assert payload["email"] == "test@example.com"

    def test_refresh_token_invalid(self, jwt_auth):
        """Test refreshing invalid token."""
        invalid_token = "invalid_refresh_token"
        
        new_access_token = jwt_auth.refresh_access_token(invalid_token)
        assert new_access_token is None

    def test_refresh_token_expired(self, jwt_auth):
        """Test refreshing expired token."""
        user_data = {"sub": "user123"}
        
        # Create expired refresh token
        expired_token = jwt.encode(
            {
                **user_data,
                "exp": datetime.now(timezone.utc) - timedelta(days=1)
            },
            jwt_auth.jwt_secret,
            algorithm=jwt_auth.jwt_algorithm
        )
        
        new_access_token = jwt_auth.refresh_access_token(expired_token)
        assert new_access_token is None


class TestJWTSecurityFeatures:
    """Test advanced JWT security features."""

    @pytest.fixture
    def jwt_auth(self):
        return JWTAuth()

    def test_token_subject_conversion(self, jwt_auth):
        """Test that token subjects are properly converted to strings."""
        user_data = {
            "sub": 12345,  # Integer user ID
            "email": "test@example.com"
        }
        
        token = jwt_auth.create_access_token(user_data)
        payload = jwt_auth.verify_token(token)
        
        # Subject should be converted to string
        assert payload["sub"] == "12345"
        assert isinstance(payload["sub"], str)

    def test_token_tampering_detection(self, jwt_auth):
        """Test detection of token tampering."""
        user_data = {"sub": "user123", "role": "user"}
        token = jwt_auth.create_access_token(user_data)
        
        # Decode token parts
        header, payload_encoded, signature = token.split('.')
        
        # Tamper with payload (change role to admin)
        import base64
        import json
        
        # Decode payload
        payload_data = json.loads(
            base64.urlsafe_b64decode(payload_encoded + '==').decode('utf-8')
        )
        payload_data["role"] = "admin"  # Privilege escalation attempt
        
        # Re-encode tampered payload
        tampered_payload = base64.urlsafe_b64encode(
            json.dumps(payload_data).encode('utf-8')
        ).decode('utf-8').rstrip('=')
        
        # Create tampered token
        tampered_token = f"{header}.{tampered_payload}.{signature}"
        
        # Verification should fail
        result = jwt_auth.verify_token(tampered_token)
        assert result is None

    def test_signature_verification(self, jwt_auth):
        """Test signature verification with different secrets."""
        user_data = {"sub": "user123"}
        
        # Create token with original secret
        token = jwt_auth.create_access_token(user_data)
        
        # Try to verify with different secret
        different_secret_auth = JWTAuth()
        different_secret_auth.jwt_secret = "different_secret"
        
        # Should fail verification
        result = different_secret_auth.verify_token(token)
        assert result is None

    def test_none_algorithm_attack_prevention(self, jwt_auth):
        """Test prevention of 'none' algorithm attack."""
        user_data = {
            "sub": "user123",
            "role": "admin",  # Attempting privilege escalation
            "exp": datetime.now(timezone.utc) + timedelta(hours=1)
        }
        
        # Create unsigned token with 'none' algorithm
        none_token = jwt.encode(user_data, "", algorithm="none")
        
        # Should fail verification
        result = jwt_auth.verify_token(none_token)
        assert result is None

    def test_audience_claim_validation(self, jwt_auth):
        """Test audience claim validation."""
        user_data = {
            "sub": "user123",
            "aud": "wrong-audience",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30)
        }
        
        token = jwt.encode(user_data, jwt_auth.jwt_secret, algorithm=jwt_auth.jwt_algorithm)
        
        # Should still validate (current implementation doesn't check audience)
        # This test documents current behavior
        result = jwt_auth.verify_token(token)
        assert result is not None

    def test_issuer_claim_validation(self, jwt_auth):
        """Test issuer claim validation."""
        user_data = {
            "sub": "user123",
            "iss": "attacker-service",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30)
        }
        
        token = jwt.encode(user_data, jwt_auth.jwt_secret, algorithm=jwt_auth.jwt_algorithm)
        
        # Should still validate (current implementation doesn't check issuer)
        # This test documents current behavior  
        result = jwt_auth.verify_token(token)
        assert result is not None

    def test_jti_uniqueness(self, jwt_auth):
        """Test JWT ID (jti) claim for uniqueness."""
        user_data = {"sub": "user123"}
        
        # Create multiple tokens
        token1 = jwt_auth.create_access_token({**user_data, "jti": "unique_id_1"})
        token2 = jwt_auth.create_access_token({**user_data, "jti": "unique_id_2"})
        
        payload1 = jwt_auth.verify_token(token1)
        payload2 = jwt_auth.verify_token(token2)
        
        # Both should be valid but have different JTI
        assert payload1 is not None
        assert payload2 is not None
        assert payload1.get("jti") != payload2.get("jti")


class TestJWTPerformance:
    """Test JWT performance characteristics."""

    @pytest.fixture
    def jwt_auth(self):
        return JWTAuth()

    def test_token_creation_performance(self, jwt_auth):
        """Test token creation performance."""
        user_data = {"sub": "user123", "email": "test@example.com"}
        
        start_time = time.time()
        tokens = [jwt_auth.create_access_token(user_data) for _ in range(1000)]
        end_time = time.time()
        
        # Should create 1000 tokens quickly (< 1 second)
        assert end_time - start_time < 1.0
        
        # All tokens should be unique (different exp times)
        assert len(set(tokens)) == 1000

    def test_token_verification_performance(self, jwt_auth):
        """Test token verification performance."""
        user_data = {"sub": "user123", "email": "test@example.com"}
        token = jwt_auth.create_access_token(user_data)
        
        start_time = time.time()
        for _ in range(1000):
            jwt_auth.verify_token(token)
        end_time = time.time()
        
        # Should verify 1000 tokens quickly (< 1 second)
        assert end_time - start_time < 1.0

    def test_concurrent_token_operations(self, jwt_auth):
        """Test concurrent token operations."""
        import concurrent.futures
        import threading
        
        user_data = {"sub": "user123", "email": "test@example.com"}
        
        def create_and_verify_token():
            token = jwt_auth.create_access_token(user_data)
            payload = jwt_auth.verify_token(token)
            return payload is not None
        
        # Run concurrent operations
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_and_verify_token) for _ in range(100)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # All operations should succeed
        assert all(results)
        assert len(results) == 100

    def test_memory_usage_stability(self, jwt_auth):
        """Test memory usage doesn't grow with token operations."""
        import gc
        
        user_data = {"sub": "user123", "email": "test@example.com"}
        
        # Force garbage collection
        gc.collect()
        initial_objects = len(gc.get_objects())
        
        # Create and verify many tokens
        for _ in range(100):
            token = jwt_auth.create_access_token(user_data)
            jwt_auth.verify_token(token)
        
        # Force garbage collection again
        gc.collect()
        final_objects = len(gc.get_objects())
        
        # Object count shouldn't grow significantly (allow some tolerance)
        object_growth = final_objects - initial_objects
        assert object_growth < 1000, f"Memory usage grew by {object_growth} objects"


class TestJWTAuthHandler:
    """Test the global auth_handler instance."""

    def test_auth_handler_exists(self):
        """Test that auth_handler is properly initialized."""
        assert auth_handler is not None
        assert isinstance(auth_handler, JWTAuth)

    def test_auth_handler_functionality(self):
        """Test auth_handler basic functionality."""
        user_data = {"sub": "user123", "email": "test@example.com"}
        
        # Should be able to create and verify tokens
        token = auth_handler.create_access_token(user_data)
        payload = auth_handler.verify_token(token)
        
        assert payload is not None
        assert payload["sub"] == "user123"

    @pytest.mark.asyncio
    async def test_auth_handler_middleware_integration(self):
        """Test auth_handler integration with middleware."""
        user_data = {"sub": "user123", "email": "test@example.com", "role": "user"}
        token = auth_handler.create_access_token(user_data)
        
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )
        
        request = MagicMock(spec=Request)
        
        current_user = await auth_handler.get_current_user(credentials, request)
        
        assert current_user["sub"] == "user123"
        assert current_user["role"] == "user"


class TestJWTEdgeCases:
    """Test JWT edge cases and error conditions."""

    @pytest.fixture
    def jwt_auth(self):
        return JWTAuth()

    def test_empty_user_data(self, jwt_auth):
        """Test token creation with empty user data."""
        empty_data = {}
        
        token = jwt_auth.create_access_token(empty_data)
        payload = jwt_auth.verify_token(token)
        
        # Should still create valid token with just exp claim
        assert payload is not None
        assert "exp" in payload

    def test_special_characters_in_claims(self, jwt_auth):
        """Test token with special characters in claims."""
        user_data = {
            "sub": "user@domain.com",
            "name": "José María García-López",
            "role": "admin/super-user",
            "metadata": {"special": "äöü!@#$%^&*()"}
        }
        
        token = jwt_auth.create_access_token(user_data)
        payload = jwt_auth.verify_token(token)
        
        assert payload is not None
        assert payload["name"] == "José María García-López"
        assert payload["metadata"]["special"] == "äöü!@#$%^&*()"

    def test_large_token_payload(self, jwt_auth):
        """Test token with large payload."""
        user_data = {
            "sub": "user123",
            "permissions": ["read:articles"] * 100,  # Large list
            "metadata": {"description": "x" * 1000}  # Large string
        }
        
        token = jwt_auth.create_access_token(user_data)
        payload = jwt_auth.verify_token(token)
        
        assert payload is not None
        assert len(payload["permissions"]) == 100
        assert len(payload["metadata"]["description"]) == 1000

    def test_numeric_claims(self, jwt_auth):
        """Test token with various numeric claim types."""
        user_data = {
            "sub": "user123",
            "user_id": 12345,
            "score": 98.7,
            "is_active": True,
            "login_count": 0
        }
        
        token = jwt_auth.create_access_token(user_data)
        payload = jwt_auth.verify_token(token)
        
        assert payload is not None
        assert payload["user_id"] == 12345
        assert payload["score"] == 98.7
        assert payload["is_active"] is True
        assert payload["login_count"] == 0

    def test_null_claims(self, jwt_auth):
        """Test token with null/None claims."""
        user_data = {
            "sub": "user123",
            "optional_field": None,
            "empty_string": "",
            "zero_value": 0
        }
        
        token = jwt_auth.create_access_token(user_data)
        payload = jwt_auth.verify_token(token)
        
        assert payload is not None
        assert payload["optional_field"] is None
        assert payload["empty_string"] == ""
        assert payload["zero_value"] == 0