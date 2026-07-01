"""
Comprehensive Performance & Security Penetration Testing - Issue #476 Phase 5.

Tests all performance and security penetration requirements:
- Authentication performance under high load
- Security middleware processing overhead
- Brute force attack protection testing
- Token tampering and privilege escalation testing
- OWASP Top 10 compliance validation
- Concurrent access and race condition testing
- Security boundary stress testing

This suite is written against the REAL source API:
- src.api.auth.permissions exposes module-level ``has_permission(role_str, perm)``,
  ``get_user_permissions(role_str)`` and ``PermissionChecker`` (no PermissionManager).
- src.api.rbac.rbac_system exposes the global ``rbac_manager`` whose
  ``permission_manager`` (a RolePermissionManager) provides ``get_role_permissions``
  and ``has_permission``.
"""

import base64
import concurrent.futures
import json
import random
import string
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest

# Import the REAL security symbols under test.
from src.api.auth.api_key_manager import APIKeyGenerator, APIKeyManager, APIKeyStatus
from src.api.auth.audit_log import SecurityAuditLogger
from src.api.auth.jwt_auth import JWTAuth
from src.api.auth.permissions import (
    Permission,
    PermissionChecker,
    get_user_permissions,
    has_permission,
)
from src.api.rbac.rbac_system import (
    Permission as RBACPermission,
    RBACManager,
    UserRole,
    rbac_manager,
)


def user_has_permission(user: dict, permission: Permission) -> bool:
    """Check whether a user dict has a permission via the real role API.

    ``permissions.has_permission`` takes a *role string* (not a user dict).
    A user object is malformed input from an attacker's perspective, so an
    unhashable role (list/dict) legitimately raises ``TypeError`` on the
    ``role not in ROLE_PERMISSIONS`` membership test - which we treat as a
    denial (returns False) rather than a granted permission.
    """
    role = user.get("role")
    try:
        return has_permission(role, permission)
    except TypeError:
        # Unhashable role (e.g. list/dict injection payload) -> denied.
        return False


class TestAuthenticationPerformanceUnderLoad:
    """Test authentication system performance under high load scenarios."""

    @pytest.fixture
    def performance_auth_system(self):
        """Set up authentication system for performance testing."""
        return {
            "jwt_auth": JWTAuth(),
            "api_key_manager": APIKeyManager(),
        }

    def test_jwt_token_creation_performance(self, performance_auth_system):
        """Test JWT token creation performance under load."""
        jwt_auth = performance_auth_system["jwt_auth"]

        user_data = {"sub": "user123", "email": "test@example.com", "role": "editor"}

        start_time = time.time()
        tokens = []
        for _ in range(1000):
            tokens.append(jwt_auth.create_access_token(user_data))
        duration = time.time() - start_time

        # Should create 1000 tokens in under 5 seconds.
        assert duration < 5.0, f"JWT creation too slow: {duration}s for 1000 tokens"
        # Each token gets a random jti, so all 1000 are unique.
        assert len(set(tokens)) == 1000, "Tokens should be unique"

        for i in range(0, 100, 10):
            payload = jwt_auth.verify_token(tokens[i])
            assert payload is not None
            assert payload["sub"] == "user123"

    def test_jwt_token_verification_performance(self, performance_auth_system):
        """Test JWT token verification performance under load."""
        jwt_auth = performance_auth_system["jwt_auth"]

        user_data = {"sub": "user123", "email": "test@example.com", "role": "admin"}
        test_tokens = [jwt_auth.create_access_token(user_data) for _ in range(100)]

        start_time = time.time()
        verification_results = []
        for token in test_tokens:
            for _ in range(20):  # 2000 total verifications
                payload = jwt_auth.verify_token(token)
                verification_results.append(payload is not None)
        duration = time.time() - start_time

        assert duration < 5.0, (
            f"JWT verification too slow: {duration}s for 2000 verifications"
        )
        assert all(verification_results), "All token verifications should succeed"

    def test_api_key_generation_performance(self, performance_auth_system):
        """Test API key generation performance under load."""
        start_time = time.time()
        api_keys = [APIKeyGenerator.generate_api_key() for _ in range(5000)]
        duration = time.time() - start_time

        assert duration < 5.0, (
            f"API key generation too slow: {duration}s for 5000 keys"
        )
        assert len(set(api_keys)) == 5000, "All API keys should be unique"

        for key in api_keys[:100]:
            assert key.startswith("nn_"), f"Invalid key format: {key}"
            assert len(key) >= 46, f"Key too short: {key}"

    def test_permission_checking_performance(self, performance_auth_system):
        """Test permission checking performance under load."""
        # Roles that exist in permissions.ROLE_PERMISSIONS.
        test_users = (
            [{"role": "admin", "user_id": f"admin_{i}"} for i in range(100)]
            + [{"role": "editor", "user_id": f"editor_{i}"} for i in range(200)]
            + [{"role": "user", "user_id": f"user_{i}"} for i in range(500)]
        )

        test_permissions = [
            Permission.READ_ARTICLES,
            Permission.CREATE_ARTICLES,
            Permission.MANAGE_SYSTEM,
            Permission.VIEW_METRICS,
            Permission.RUN_NLP_JOBS,
        ]

        start_time = time.time()
        permission_checks = 0
        for user in test_users:
            for permission in test_permissions:
                has_perm = user_has_permission(user, permission)
                permission_checks += 1
                if user["role"] == "admin":
                    # Admin has ALL permissions in ROLE_PERMISSIONS.
                    assert has_perm is True, f"Admin should have {permission}"
        duration = time.time() - start_time

        assert permission_checks == 4000
        assert duration < 2.0, (
            f"Permission checking too slow: {duration}s for {permission_checks} checks"
        )

    def test_concurrent_authentication_performance(self, performance_auth_system):
        """Test concurrent authentication performance."""
        jwt_auth = performance_auth_system["jwt_auth"]

        def authenticate_user(user_id):
            user_data = {"sub": f"user_{user_id}", "role": "editor"}
            token = jwt_auth.create_access_token(user_data)
            for _ in range(10):
                if jwt_auth.verify_token(token) is None:
                    return False
            return True

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(authenticate_user, i) for i in range(200)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        duration = time.time() - start_time

        assert duration < 10.0, f"Concurrent auth too slow: {duration}s for 200 users"
        assert all(results), "All concurrent authentications should succeed"

    def test_mixed_authentication_load(self, performance_auth_system):
        """Test mixed authentication operations under load."""
        jwt_auth = performance_auth_system["jwt_auth"]

        def mixed_auth_operations():
            results = []
            for i in range(50):
                # JWT operations
                user_data = {"sub": f"load_user_{i}", "role": "editor"}
                token = jwt_auth.create_access_token(user_data)
                results.append(jwt_auth.verify_token(token) is not None)

                # Permission checks
                user = {"role": "editor", "user_id": f"user_{i}"}
                results.append(user_has_permission(user, Permission.READ_ARTICLES))

                # API key operations
                api_key = APIKeyGenerator.generate_api_key()
                key_hash = APIKeyGenerator.hash_api_key(api_key)
                results.append(APIKeyGenerator.verify_api_key(api_key, key_hash))
            return results

        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(mixed_auth_operations) for _ in range(10)]
            all_results = []
            for future in concurrent.futures.as_completed(futures):
                all_results.extend(future.result())
        duration = time.time() - start_time

        # This exercises 500 hash+verify pairs. hash_api_key uses PBKDF2 with
        # 100k iterations (intentionally slow, ~50ms per hash+verify pair) and
        # is CPU-bound, so the GIL serialises it regardless of thread count.
        # The ceiling here catches a gross (>~1.6x) regression while remaining
        # achievable for the real, deliberately-expensive hashing cost.
        assert duration < 40.0, f"Mixed auth load too slow: {duration}s"
        assert all(all_results), "All mixed auth operations should succeed"


class TestSecurityPenetrationTesting:
    """Test security system against penetration testing scenarios."""

    @pytest.fixture
    def security_test_system(self):
        """Set up security system for penetration testing."""
        return {
            "jwt_auth": JWTAuth(),
            "rbac_system": rbac_manager,
            "audit_logger": SecurityAuditLogger(),
        }

    def test_brute_force_attack_protection(self, security_test_system):
        """Test protection against brute force attacks."""
        jwt_auth = security_test_system["jwt_auth"]

        failed_attempts = 0
        successful_attempts = 0

        for _ in range(1000):
            fake_token = (
                "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."
                + "".join(random.choices(string.ascii_letters + string.digits, k=100))
                + "."
                + "".join(random.choices(string.ascii_letters + string.digits, k=50))
            )
            if jwt_auth.verify_token(fake_token) is None:
                failed_attempts += 1
            else:
                successful_attempts += 1

        assert failed_attempts == 1000, "Should reject all brute force attempts"
        assert successful_attempts == 0, "No brute force attempts should succeed"

    def test_token_tampering_detection(self, security_test_system):
        """Test detection of token tampering attempts."""
        jwt_auth = security_test_system["jwt_auth"]

        user_data = {"sub": "user123", "role": "user"}
        valid_token = jwt_auth.create_access_token(user_data)

        original_payload = jwt_auth.verify_token(valid_token)
        assert original_payload is not None
        assert original_payload["role"] == "user"

        token_parts = valid_token.split(".")
        tampering_attempts = [
            # Tamper header
            f"{token_parts[0]}X.{token_parts[1]}.{token_parts[2]}",
            # Tamper payload
            f"{token_parts[0]}.{token_parts[1]}Y.{token_parts[2]}",
            # Tamper signature
            f"{token_parts[0]}.{token_parts[1]}.{token_parts[2]}Z",
        ]

        for i, tampered_token in enumerate(tampering_attempts):
            payload = jwt_auth.verify_token(tampered_token)
            assert payload is None, (
                f"Tampered token {i + 1} was accepted: {tampered_token[:50]}..."
            )

    def test_privilege_escalation_attempts(self, security_test_system):
        """Test prevention of privilege escalation attempts."""
        # A low-privilege "user" role must not reach admin-only permissions.
        low_priv_user = {"role": "user", "user_id": "attacker123"}

        admin_permissions = [
            Permission.MANAGE_SYSTEM,
            Permission.DELETE_USERS,
            Permission.CREATE_USERS,
            Permission.DELETE_ARTICLES,
        ]

        escalation_successes = [
            perm
            for perm in admin_permissions
            if user_has_permission(low_priv_user, perm)
        ]
        assert escalation_successes == [], (
            f"Privilege escalation detected: {escalation_successes}"
        )

        # Manipulated user objects must never be granted MANAGE_SYSTEM.
        # Only the exact string "admin" maps to the admin role.
        manipulated_users = [
            {"role": ["admin"], "user_id": "attacker123"},  # unhashable list
            {"role": "ADMIN", "user_id": "attacker123"},  # case manipulation
            {"role": "admin\x00", "user_id": "attacker123"},  # null-byte injection
            {"role": " admin", "user_id": "attacker123"},  # whitespace padding
            {"role": {"$eq": "admin"}, "user_id": "attacker123"},  # unhashable dict
        ]

        for manipulated_user in manipulated_users:
            granted = user_has_permission(manipulated_user, Permission.MANAGE_SYSTEM)
            assert granted is False, (
                f"Accepted manipulated user: {manipulated_user}"
            )

    def test_session_hijacking_protection(self, security_test_system):
        """Test protection against session hijacking."""
        jwt_auth = security_test_system["jwt_auth"]

        user1_data = {"sub": "user1", "role": "editor", "session_id": "session_123"}
        user2_data = {"sub": "user2", "role": "user", "session_id": "session_456"}

        token1 = jwt_auth.create_access_token(user1_data)
        token2 = jwt_auth.create_access_token(user2_data)

        payload1 = jwt_auth.verify_token(token1)
        payload2 = jwt_auth.verify_token(token2)

        assert payload1["sub"] == "user1"
        assert payload2["sub"] == "user2"

        # Tokens must remain bound to distinct users/sessions and be unforgeable
        # across each other (a per-token jti also differentiates them).
        assert payload1["session_id"] != payload2["session_id"]
        assert payload1["sub"] != payload2["sub"]
        assert payload1["jti"] != payload2["jti"]

    def test_timing_attack_resistance(self, security_test_system):
        """Test resistance to timing attacks in API key verification."""
        valid_key = APIKeyGenerator.generate_api_key()
        valid_hash = APIKeyGenerator.hash_api_key(valid_key)

        invalid_keys = [
            "nn_invalid_key_123",
            "nn_wrong_key_456",
            "nn_fake_key_789",
            "nn_" + "x" * 50,  # different length
            "",  # empty key
        ]

        valid_times = []
        for _ in range(100):
            start = time.perf_counter()
            APIKeyGenerator.verify_api_key(valid_key, valid_hash)
            valid_times.append(time.perf_counter() - start)

        invalid_times = []
        for invalid_key in invalid_keys:
            for _ in range(20):
                start = time.perf_counter()
                APIKeyGenerator.verify_api_key(invalid_key, valid_hash)
                invalid_times.append(time.perf_counter() - start)

        avg_valid_time = sum(valid_times) / len(valid_times)
        avg_invalid_time = sum(invalid_times) / len(invalid_times)

        # verify_api_key uses hmac.compare_digest (constant time), so valid and
        # invalid verifications should take comparable time.
        time_ratio = max(avg_valid_time, avg_invalid_time) / min(
            avg_valid_time, avg_invalid_time
        )
        assert time_ratio < 3.0, (
            f"Potential timing attack vector: {time_ratio}x difference"
        )

    def test_injection_attack_prevention(self, security_test_system):
        """Test prevention of various injection attacks in role handling."""
        injection_payloads = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "'; INSERT INTO permissions VALUES ('admin'); --",
            "admin' UNION SELECT * FROM secrets --",
            "'; DELETE FROM roles; --",
        ]

        for payload in injection_payloads:
            malicious_user = {"role": payload, "user_id": f"attacker_{payload[:10]}"}
            # None of these strings are valid roles -> permission denied.
            has_perm = user_has_permission(malicious_user, Permission.READ_ARTICLES)
            assert has_perm is False, f"Accepted injection payload: {payload}"

    def test_concurrent_attack_simulation(self, security_test_system):
        """Test system under concurrent attack simulation."""
        jwt_auth = security_test_system["jwt_auth"]

        def attack_simulation():
            attack_results = {
                "brute_force_blocked": 0,
                "privilege_escalation_blocked": 0,
                "token_tampering_blocked": 0,
            }

            # Brute force simulation
            for _ in range(50):
                fake_token = "".join(random.choices(string.ascii_letters, k=100))
                if jwt_auth.verify_token(fake_token) is None:
                    attack_results["brute_force_blocked"] += 1

            # Privilege escalation simulation
            for _ in range(20):
                fake_user = {"role": "user", "user_id": "attacker"}
                if not user_has_permission(fake_user, Permission.MANAGE_SYSTEM):
                    attack_results["privilege_escalation_blocked"] += 1

            # Token tampering simulation
            valid_token = jwt_auth.create_access_token(
                {"sub": "test", "role": "user"}
            )
            for _ in range(30):
                tampered = valid_token + random.choice(string.ascii_letters)
                if jwt_auth.verify_token(tampered) is None:
                    attack_results["token_tampering_blocked"] += 1

            return attack_results

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(attack_simulation) for _ in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        total_results = {
            "brute_force_blocked": sum(r["brute_force_blocked"] for r in results),
            "privilege_escalation_blocked": sum(
                r["privilege_escalation_blocked"] for r in results
            ),
            "token_tampering_blocked": sum(
                r["token_tampering_blocked"] for r in results
            ),
        }

        assert total_results["brute_force_blocked"] == 500  # 10 x 50
        assert total_results["privilege_escalation_blocked"] == 200  # 10 x 20
        assert total_results["token_tampering_blocked"] == 300  # 10 x 30


class TestOWASPTop10Compliance:
    """Test compliance with OWASP Top 10 security vulnerabilities."""

    @pytest.fixture
    def owasp_test_system(self):
        """Set up system for OWASP Top 10 testing."""
        return {
            "jwt_auth": JWTAuth(),
            "api_key_generator": APIKeyGenerator(),
            "rbac_system": rbac_manager,
        }

    def test_a01_broken_access_control(self, owasp_test_system):
        """Test A01: Broken Access Control prevention."""
        # Two distinct low-privilege users; neither reaches admin functions.
        user_a = {"role": "user", "user_id": "user_a"}
        user_b = {"role": "user", "user_id": "user_b"}

        admin_functions = [Permission.MANAGE_SYSTEM, Permission.DELETE_USERS]
        for perm in admin_functions:
            assert not user_has_permission(user_a, perm)
            assert not user_has_permission(user_b, perm)

        # Vertical escalation: a "user" must not gain editor/admin perms.
        low_priv_user = {"role": "user", "user_id": "test_user"}
        elevated_perms = [Permission.RUN_NLP_JOBS, Permission.VIEW_METRICS]
        for perm in elevated_perms:
            assert not user_has_permission(low_priv_user, perm)

    def test_a02_cryptographic_failures(self, owasp_test_system):
        """Test A02: Cryptographic Failures prevention."""
        jwt_auth = owasp_test_system["jwt_auth"]
        api_key_gen = owasp_test_system["api_key_generator"]

        user_data = {"sub": "test_user", "role": "editor"}
        token = jwt_auth.create_access_token(user_data)

        parts = token.split(".")
        assert len(parts) == 3, "JWT should have 3 parts"

        header = json.loads(base64.urlsafe_b64decode(parts[0] + "==="))
        assert header.get("alg") != "none", "JWT should not use 'none' algorithm"
        assert header.get("alg") in ["HS256", "RS256", "ES256"], (
            f"Insecure algorithm: {header.get('alg')}"
        )

        # Secure randomness -> unique keys.
        keys = [api_key_gen.generate_api_key() for _ in range(100)]
        assert len(set(keys)) == 100, "All keys should be unique (secure randomness)"

        # Deterministic, salted hashing producing a 64-hex-char digest.
        test_key = "nn_test_key_123"
        hash1 = api_key_gen.hash_api_key(test_key)
        hash2 = api_key_gen.hash_api_key(test_key)
        assert hash1 == hash2, "Same key should produce same hash"
        assert len(hash1) == 64, "Should produce a 64 hex char digest"
        assert all(c in "0123456789abcdef" for c in hash1), "Digest must be hex"

    def test_a03_injection_prevention(self, owasp_test_system):
        """Test A03: Injection prevention."""
        sql_payloads = [
            "admin'; DROP TABLE users; --",
            "admin' OR '1'='1",
            "admin' UNION SELECT * FROM secrets",
            "'; INSERT INTO permissions VALUES('admin'); --",
        ]
        for payload in sql_payloads:
            user = {"role": payload, "user_id": "attacker"}
            has_perm = user_has_permission(user, Permission.READ_ARTICLES)
            assert has_perm is False, f"SQL injection payload accepted: {payload}"

        # NoSQL-style dict payloads are unhashable roles -> safely denied.
        nosql_payloads = [
            {"$ne": None},
            {"$gt": ""},
            {"$regex": ".*"},
            {"$where": "1==1"},
        ]
        for payload in nosql_payloads:
            user = {"role": payload, "user_id": "attacker"}
            has_perm = user_has_permission(user, Permission.READ_ARTICLES)
            assert has_perm is False, f"NoSQL injection payload accepted: {payload}"

    def test_a04_insecure_design_prevention(self, owasp_test_system):
        """Test A04: Insecure Design prevention."""
        jwt_auth = owasp_test_system["jwt_auth"]
        rbac_system = owasp_test_system["rbac_system"]

        # Fail-safe defaults: unknown roles get no permissions.
        permissions = rbac_system.permission_manager.get_role_permissions("unknown")
        assert permissions == set(), "Unknown roles should have no permissions"

        # Least privilege: FREE users have minimal permissions.
        free_perms = rbac_system.permission_manager.get_role_permissions(
            UserRole.FREE
        )
        assert len(free_perms) <= 5, (
            f"Free users have too many permissions: {len(free_perms)}"
        )

        # Defense in depth: expired tokens are rejected.
        # create_access_token always sets its own future exp, so build an
        # already-expired token manually to exercise expiry validation.
        expired_token = jwt.encode(
            {
                "sub": "test",
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            },
            jwt_auth.jwt_secret,
            algorithm=jwt_auth.jwt_algorithm,
        )
        assert jwt_auth.verify_token(expired_token) is None, (
            "Expired token should be rejected"
        )

    def test_a05_security_misconfiguration(self, owasp_test_system):
        """Test A05: Security Misconfiguration prevention."""
        jwt_auth = owasp_test_system["jwt_auth"]

        assert jwt_auth.jwt_algorithm == "HS256", "Should use secure algorithm"
        assert jwt_auth.access_token_expire > 0, "Tokens should expire"
        assert jwt_auth.access_token_expire <= 1440, "Tokens shouldn't live too long"

        assert jwt_auth.jwt_secret != "secret", "Should not use trivial default secret"
        assert jwt_auth.jwt_secret != "", "Secret should not be empty"
        assert len(jwt_auth.jwt_secret) >= 8, "Secret should be reasonably long"

    def test_a06_vulnerable_components(self, owasp_test_system):
        """Test A06: Vulnerable and Outdated Components prevention."""
        jwt_auth = owasp_test_system["jwt_auth"]

        malformed_tokens = [
            "not.a.jwt",
            "too.few.parts",
            "too.many.parts.here.extra",
            "",
            None,
        ]
        for token in malformed_tokens:
            payload = jwt_auth.verify_token(token)
            assert payload is None, f"Malformed token should be rejected: {token}"

    def test_a07_identification_authentication_failures(self, owasp_test_system):
        """Test A07: Identification and Authentication Failures prevention."""
        jwt_auth = owasp_test_system["jwt_auth"]
        api_key_gen = owasp_test_system["api_key_generator"]

        keys = [api_key_gen.generate_api_key() for _ in range(1000)]

        # Randomness distribution: no single first-char dominates.
        first_chars = [key[3] for key in keys]  # skip "nn_" prefix
        char_counts = {}
        for char in first_chars:
            char_counts[char] = char_counts.get(char, 0) + 1
        max_count = max(char_counts.values())
        assert max_count < 80, (
            f"Poor randomness detected: {max_count}/1000 for one character"
        )

        # Session uniqueness: two tokens for the same user differ (random jti).
        user_data = {"sub": "test_user", "role": "editor"}
        token1 = jwt_auth.create_access_token(user_data)
        token2 = jwt_auth.create_access_token(user_data)
        assert token1 != token2, "Sessions should be unique even for same user"

    def test_a10_server_side_request_forgery(self, owasp_test_system):
        """Test A10: Server-Side Request Forgery (SSRF) prevention."""
        # User-controlled data (URLs/internal addresses) must not be trusted
        # as roles and must not grant permissions.
        ssrf_payloads = [
            "http://localhost:8080/admin",
            "https://169.254.169.254/metadata",  # AWS metadata service
            "file:///etc/passwd",
            "ftp://internal.server/data",
            "ldap://internal.server/search",
        ]
        for payload in ssrf_payloads:
            user = {
                "role": payload,
                "user_id": payload,
                "metadata": {"url": payload},
            }
            has_perm = user_has_permission(user, Permission.READ_ARTICLES)
            assert has_perm is False, f"SSRF payload granted access: {payload}"


class TestRaceConditionAndConcurrency:
    """Test race conditions and concurrent access scenarios."""

    @pytest.fixture
    def concurrency_test_system(self):
        """Set up system for concurrency testing."""
        return {
            "jwt_auth": JWTAuth(),
            "api_key_manager": APIKeyManager(),
            "rbac_system": rbac_manager,
        }

    def test_concurrent_token_operations(self, concurrency_test_system):
        """Test concurrent JWT token operations."""
        jwt_auth = concurrency_test_system["jwt_auth"]

        def token_operations():
            results = []
            user_data = {
                "sub": f"user_{threading.current_thread().ident}",
                "role": "editor",
            }
            for _ in range(100):
                token = jwt_auth.create_access_token(user_data)
                results.append(jwt_auth.verify_token(token) is not None)

                refresh_token = jwt_auth.create_refresh_token(user_data)
                new_token = jwt_auth.refresh_access_token(refresh_token)
                results.append(new_token is not None)
            return all(results)

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(token_operations) for _ in range(20)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert all(results), "Some concurrent token operations failed"

    def test_concurrent_permission_checks(self, concurrency_test_system):
        """Test concurrent permission checking."""
        test_users = [
            {"role": "admin", "user_id": "admin_1"},
            {"role": "editor", "user_id": "editor_1"},
            {"role": "user", "user_id": "user_1"},
        ]
        test_permissions = list(Permission)

        def permission_check_worker():
            results = []
            for _ in range(200):
                user = random.choice(test_users)
                perm = random.choice(test_permissions)
                has_perm = user_has_permission(user, perm)

                if user["role"] == "admin":
                    # Admin has every permission.
                    results.append(has_perm is True)
                elif user["role"] == "user" and perm == Permission.MANAGE_SYSTEM:
                    # Basic users never have MANAGE_SYSTEM.
                    results.append(has_perm is False)
                else:
                    results.append(isinstance(has_perm, bool))
            return all(results)

        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(permission_check_worker) for _ in range(15)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert all(results), "Concurrent permission checks were inconsistent"

    def test_concurrent_role_permission_reads(self, concurrency_test_system):
        """Test the global RBAC manager under concurrent role permission reads.

        The former test used non-existent async role-assignment methods. This
        replaces it with a genuine concurrency test over the real, thread-safe
        read path: many threads call ``get_role_permissions`` concurrently and
        must always observe a consistent role hierarchy.
        """
        rbac_system = concurrency_test_system["rbac_system"]

        def role_read_worker():
            results = []
            for _ in range(50):
                admin_perms = rbac_system.permission_manager.get_role_permissions(
                    UserRole.ADMIN
                )
                free_perms = rbac_system.permission_manager.get_role_permissions(
                    UserRole.FREE
                )
                # FREE inherits into ADMIN, and ADMIN is strictly larger.
                results.append(free_perms.issubset(admin_perms))
                results.append(len(admin_perms) > len(free_perms))
                results.append(RBACPermission.READ_ARTICLES in free_perms)
            return all(results)

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(role_read_worker) for _ in range(50)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 50
        assert all(results), "Concurrent role permission reads were inconsistent"

    def test_thread_safety_of_global_managers(self, concurrency_test_system):
        """Test thread safety of global manager instances."""
        thread_results = {}

        def worker_thread(idx):
            results = []
            for _ in range(100):
                admin_perms = rbac_manager.permission_manager.get_role_permissions(
                    UserRole.ADMIN
                )
                free_perms = rbac_manager.permission_manager.get_role_permissions(
                    UserRole.FREE
                )
                results.append(len(admin_perms) > len(free_perms))
                results.append(free_perms.issubset(admin_perms))
            thread_results[idx] = all(results)

        threads = [
            threading.Thread(target=worker_thread, args=(i,)) for i in range(10)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(thread_results) == 10, "Every thread should record a result"
        assert all(thread_results.values()), "Thread safety test failed"


def test_permission_checker_and_get_user_permissions_consistency():
    """PermissionChecker and get_user_permissions agree with has_permission."""
    for role in ("admin", "editor", "user"):
        perms = get_user_permissions(role)
        checker = PermissionChecker(role)
        for perm in Permission:
            expected = perm in perms
            assert checker.can(perm) is expected
            assert has_permission(role, perm) is expected

    # Unknown role: no permissions at all.
    assert get_user_permissions("nonexistent") == set()
    checker = PermissionChecker("nonexistent")
    assert all(not checker.can(perm) for perm in Permission)
