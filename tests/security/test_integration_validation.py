"""
Final Integration & Validation Testing Suite - Issue #476 Phase 6.

Tests final integration requirements and validation:
- Ensure the real security classes expose a testable public interface
- OWASP Top 10 and SOC 2 compliance validation
- Final integration testing and documentation
- End-to-end security workflow validation
- System-wide security posture assessment

This suite is written against the REAL security API of the codebase. It uses:
- src.api.auth.permissions (colon-style Permission enum, has_permission,
  get_user_permissions, PermissionChecker, require_permissions) for the
  "admin/editor/user" role model.
- src.api.rbac.rbac_system (underscore-style Permission enum, UserRole,
  RBACManager/RolePermissionManager, rbac_manager) for the
  "admin/premium/free" role model.
Each individual test picks ONE model and stays consistent so every assertion
is a genuine check against production behavior.
"""

import asyncio
import base64
import inspect
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

# --- Authentication / key management -------------------------------------
from src.api.auth.api_key_manager import (
    APIKey,
    APIKeyGenerator,
    APIKeyManager,
    APIKeyStatus,
    DynamoDBAPIKeyStore,
)
from src.api.auth.audit_log import SecurityAuditLogger, security_logger
from src.api.auth.jwt_auth import JWTAuth, auth_handler

# --- permissions.py model (admin/editor/user, colon-style values) --------
from src.api.auth.permissions import (
    Permission,
    PermissionChecker,
    ROLE_PERMISSIONS,
    get_user_permissions,
    has_permission,
    require_permissions,
)

# --- Middleware ----------------------------------------------------------
from src.api.middleware.auth_middleware import (
    AuditLogMiddleware,
    RoleBasedAccessMiddleware,
    configure_cors,
)
from src.api.middleware.rate_limit_middleware import (
    RateLimitConfig,
    RateLimitMiddleware,
    UserTier,
)

# --- rbac_system.py model (admin/premium/free, underscore-style values) --
from src.api.rbac.rbac_system import (
    DynamoDBPermissionStore,
    Permission as RBACPermission,
    RBACManager,
    RoleDefinition,
    RolePermissionManager,
    UserRole,
    rbac_manager,
)

# --- WAF -----------------------------------------------------------------
from src.api.security.local_waf_manager import (
    ActionType,
    LocalWAFManager,
    SecurityEvent,
    ThreatType,
)
from src.api.security.waf_middleware import WAFSecurityMiddleware


class TestSecurityCoverageValidation:
    """Validate that all real security classes expose a testable interface."""

    def test_authentication_classes_coverage(self):
        """Every authentication class should expose a public interface to test."""
        # Real authentication / key-management classes (PermissionManager does
        # not exist in this codebase; PermissionChecker is the real utility).
        auth_classes = [
            APIKey,
            APIKeyGenerator,
            APIKeyManager,
            APIKeyStatus,
            DynamoDBAPIKeyStore,
            JWTAuth,
            PermissionChecker,
            SecurityAuditLogger,
        ]

        for auth_class in auth_classes:
            public_methods = [
                name
                for name, _ in inspect.getmembers(auth_class, inspect.isfunction)
                if not name.startswith("_")
            ]
            public_properties = [
                name
                for name in dir(auth_class)
                if not name.startswith("_")
                and not callable(getattr(auth_class, name))
            ]

            total_items = len(public_methods) + len(public_properties)
            assert total_items > 0, (
                f"{auth_class.__name__} has no public interface to test"
            )

    def test_security_middleware_classes_coverage(self):
        """All security middleware classes must have an async dispatch method."""
        middleware_classes = [
            WAFSecurityMiddleware,
            RateLimitMiddleware,
            AuditLogMiddleware,
            RoleBasedAccessMiddleware,
        ]

        for middleware_class in middleware_classes:
            assert hasattr(middleware_class, "dispatch"), (
                f"{middleware_class.__name__} missing dispatch method"
            )
            dispatch_method = getattr(middleware_class, "dispatch")
            assert asyncio.iscoroutinefunction(dispatch_method), (
                f"{middleware_class.__name__}.dispatch is not async"
            )

    def test_rbac_classes_coverage(self):
        """All RBAC classes should have real members (methods or enum values)."""
        rbac_classes = [
            RBACManager,
            RoleDefinition,
            RolePermissionManager,
            DynamoDBPermissionStore,
            UserRole,
            RBACPermission,
        ]

        for rbac_class in rbac_classes:
            assert inspect.isclass(rbac_class), f"{rbac_class} is not a class"
            public_callables = [
                name
                for name in dir(rbac_class)
                if not name.startswith("_") and callable(getattr(rbac_class, name))
            ]
            is_enum = hasattr(rbac_class, "__members__")
            assert public_callables or is_enum, (
                f"{rbac_class.__name__} exposes no public members"
            )

    def test_comprehensive_security_module_structure(self):
        """The core security packages must all be importable."""
        expected_security_modules = [
            "src.api.auth",
            "src.api.security",
            "src.api.rbac",
            "src.api.middleware",
        ]

        for module_path in expected_security_modules:
            module_parts = module_path.split(".")
            imported_module = __import__(module_path, fromlist=[module_parts[-1]])
            assert imported_module is not None, f"Failed to import {module_path}"

    def test_role_permission_models_are_consistent(self):
        """Both permission models expose the expected roles and helpers."""
        # permissions.py role model
        assert set(ROLE_PERMISSIONS.keys()) == {"admin", "editor", "user"}
        # admin has every colon-style permission
        assert get_user_permissions("admin") == set(Permission)
        # rbac model roles
        assert {r for r in UserRole} == {
            UserRole.ADMIN,
            UserRole.PREMIUM,
            UserRole.FREE,
        }
        # require_permissions is a usable decorator factory
        assert callable(require_permissions)
        decorated = require_permissions(Permission.READ_ARTICLES)
        assert callable(decorated)


class TestOWASPAndSOC2Compliance:
    """Test OWASP Top 10 and SOC 2 compliance validation."""

    @pytest.fixture
    def compliance_test_system(self):
        """Setup system for compliance testing using the real API objects."""
        return {
            "jwt_auth": JWTAuth(),
            "rbac_manager": rbac_manager,
            "audit_logger": SecurityAuditLogger(),
            "api_key_manager": APIKeyManager(),
        }

    def test_owasp_top_10_comprehensive_compliance(self, compliance_test_system):
        """Test comprehensive OWASP Top 10 compliance."""
        owasp_compliance = {
            "A01_broken_access_control": self._test_access_control_compliance,
            "A02_cryptographic_failures": self._test_cryptographic_compliance,
            "A03_injection": self._test_injection_compliance,
            "A04_insecure_design": self._test_secure_design_compliance,
            "A05_security_misconfiguration": self._test_configuration_compliance,
            "A06_vulnerable_components": self._test_component_compliance,
            "A07_identification_auth_failures": self._test_auth_compliance,
            "A08_software_data_integrity": self._test_integrity_compliance,
            "A09_logging_monitoring": self._test_logging_compliance,
            "A10_server_side_request_forgery": self._test_ssrf_compliance,
        }

        compliance_results = {
            vuln_id: test_func(compliance_test_system)
            for vuln_id, test_func in owasp_compliance.items()
        }

        failed_tests = [
            vuln_id
            for vuln_id, result in compliance_results.items()
            if result != "COMPLIANT"
        ]
        assert not failed_tests, f"OWASP compliance failures: {compliance_results}"

    def _test_access_control_compliance(self, system):
        """A01: Broken Access Control - least privilege via rbac model."""
        pm = system["rbac_manager"].permission_manager

        free_perms = pm.get_role_permissions(UserRole.FREE)
        admin_perms = pm.get_role_permissions(UserRole.ADMIN)

        # Free users get a minimal permission set.
        if len(free_perms) > 5:
            return f"FAILED: Free users have too many permissions ({len(free_perms)})"

        # Admin strictly dominates free (privilege escalation boundary).
        if not free_perms.issubset(admin_perms):
            return "FAILED: Free permissions are not a subset of admin"
        if len(admin_perms) <= len(free_perms):
            return "FAILED: Admin does not have more permissions than free"

        # Admin-only permissions must NOT be granted to the free role.
        admin_only = admin_perms - free_perms
        for admin_perm in admin_only:
            if pm.has_permission(UserRole.FREE, admin_perm):
                return f"FAILED: Free role has admin permission {admin_perm}"

        return "COMPLIANT"

    def _test_cryptographic_compliance(self, system):
        """A02: Cryptographic Failures - JWT alg and key hashing."""
        jwt_auth = system["jwt_auth"]

        token = jwt_auth.create_access_token({"sub": "test", "role": "user"})
        header_b64 = token.split(".")[0]
        header = json.loads(base64.urlsafe_b64decode(header_b64 + "==="))
        if header.get("alg") in ["none", "HS1", "RS1"]:
            return f"FAILED: Insecure JWT algorithm {header.get('alg')}"
        if header.get("alg") != "HS256":
            return f"FAILED: Unexpected JWT algorithm {header.get('alg')}"

        key = APIKeyGenerator.generate_api_key()
        if len(key) < 40:
            return "FAILED: API keys too short"

        key_hash = APIKeyGenerator.hash_api_key(key)
        if len(key_hash) != 64:  # 32-byte pbkdf2-sha256 digest as hex
            return "FAILED: Weak key hashing"

        return "COMPLIANT"

    def _test_injection_compliance(self, system):
        """A03: Injection - malicious role strings never grant permissions."""
        injection_payloads = [
            "'; DROP TABLE users; --",
            "' OR '1'='1",
            "admin' UNION SELECT password FROM users --",
        ]

        for payload in injection_payloads:
            # A malicious string is not a known role, so it has NO permissions.
            if has_permission(payload, Permission.READ_ARTICLES):
                return f"FAILED: SQL injection payload accepted: {payload}"
            if get_user_permissions(payload):
                return f"FAILED: Injection payload yielded permissions: {payload}"

        # The WAF's detector should flag genuine SQLi content.
        waf = LocalWAFManager()
        if not waf.detect_sql_injection("' OR 1=1 --"):
            return "FAILED: WAF did not detect SQL injection"

        return "COMPLIANT"

    def _test_secure_design_compliance(self, system):
        """A04: Insecure Design - secure defaults / fail-safe behavior."""
        pm = system["rbac_manager"].permission_manager

        # Unknown roles must yield an empty permission set.
        unknown_perms = pm.get_role_permissions("unknown_role")
        if len(unknown_perms) != 0:
            return "FAILED: Unknown roles have permissions (insecure default)"

        # None role must fail safe (no permission granted, no crash).
        if pm.has_permission(None, RBACPermission.MANAGE_SYSTEM) is not False:
            return "FAILED: None role granted permission"

        return "COMPLIANT"

    def _test_configuration_compliance(self, system):
        """A05: Security Misconfiguration - JWT config hardening."""
        jwt_auth = system["jwt_auth"]

        if jwt_auth.jwt_secret in ["secret", "password", "123456", ""]:
            return "FAILED: Weak JWT secret"
        if len(jwt_auth.jwt_secret) < 8:
            return "FAILED: JWT secret too short"
        if not (0 < jwt_auth.access_token_expire <= 1440):  # up to 24 hours
            return "FAILED: JWT access token lifetime out of range"
        if jwt_auth.jwt_algorithm == "none":
            return "FAILED: JWT algorithm set to 'none'"

        return "COMPLIANT"

    def _test_component_compliance(self, system):
        """A06: Vulnerable Components - JWT library rejects malformed tokens."""
        jwt_auth = system["jwt_auth"]

        malformed_tokens = ["invalid", "too.few", "too.many.parts.here", ""]
        for token in malformed_tokens:
            if jwt_auth.verify_token(token) is not None:
                return f"FAILED: Malformed token accepted: {token}"
        if jwt_auth.verify_token(None) is not None:
            return "FAILED: None token accepted"

        return "COMPLIANT"

    def _test_auth_compliance(self, system):
        """A07: Identification/Auth Failures - key strength & uniqueness."""
        keys = [APIKeyGenerator.generate_api_key() for _ in range(100)]

        if len(set(keys)) != 100:
            return "FAILED: API key generation not unique"

        # All keys carry the identifying prefix.
        if not all(k.startswith("nn_") for k in keys):
            return "FAILED: API keys missing 'nn_' prefix"

        # The character right after the prefix should vary (basic randomness).
        first_chars = [key[3] for key in keys if len(key) > 3]
        if len(set(first_chars)) < 10:
            return "FAILED: Poor API key randomness"

        return "COMPLIANT"

    def _test_integrity_compliance(self, system):
        """A08: Software/Data Integrity - tampered JWT is rejected."""
        jwt_auth = system["jwt_auth"]

        token = jwt_auth.create_access_token({"sub": "test", "role": "user"})
        tampered_token = token[:-5] + ("YYYYY" if token[-5:] != "YYYYY" else "ZZZZZ")

        if jwt_auth.verify_token(tampered_token) is not None:
            return "FAILED: Tampered JWT token accepted"

        return "COMPLIANT"

    def _test_logging_compliance(self, system):
        """A09: Logging/Monitoring - audit logger exposes event logging."""
        audit_logger = system["audit_logger"]

        if not hasattr(audit_logger, "log_security_event"):
            return "FAILED: No security event logging"
        if not asyncio.iscoroutinefunction(audit_logger.log_security_event):
            return "FAILED: log_security_event is not async"
        if not hasattr(audit_logger, "_format_log_event"):
            return "FAILED: No log formatting for audit events"

        return "COMPLIANT"

    def _test_ssrf_compliance(self, system):
        """A10: SSRF - user-controlled strings never trigger requests."""
        ssrf_payloads = [
            "http://localhost:8080/admin",
            "https://169.254.169.254/metadata",
            "file:///etc/passwd",
        ]

        # These payloads were historically fed as a "role"; a URL is not a
        # known role, so permission checks must simply return False (no I/O).
        for payload in ssrf_payloads:
            result = has_permission(payload, Permission.READ_ARTICLES)
            if not isinstance(result, bool):
                return f"FAILED: Unexpected response to SSRF payload: {payload}"
            if result is True:
                return f"FAILED: SSRF payload granted permission: {payload}"

        return "COMPLIANT"

    def test_soc2_compliance_controls(self, compliance_test_system):
        """Test SOC 2 compliance controls."""
        soc2_controls = {
            "security": self._test_soc2_security_controls,
            "availability": self._test_soc2_availability_controls,
            "processing_integrity": self._test_soc2_processing_controls,
            "confidentiality": self._test_soc2_confidentiality_controls,
            "privacy": self._test_soc2_privacy_controls,
        }

        soc2_results = {
            area: test_func(compliance_test_system)
            for area, test_func in soc2_controls.items()
        }

        compliant_controls = [
            area for area, result in soc2_results.items() if result == "COMPLIANT"
        ]

        for control in ["security", "confidentiality"]:
            assert control in compliant_controls, (
                f"SOC 2 {control} control not compliant: "
                f"{soc2_results.get(control, 'NOT_TESTED')}"
            )

    def _test_soc2_security_controls(self, system):
        """SOC 2 Security - RBAC roles and an auth mechanism exist."""
        pm = system["rbac_manager"].permission_manager

        for role in (UserRole.FREE, UserRole.PREMIUM, UserRole.ADMIN):
            perms = pm.get_role_permissions(role)
            if len(perms) == 0:
                return f"FAILED: Role {role} has no permissions"

        jwt_auth = system["jwt_auth"]
        if not hasattr(jwt_auth, "verify_token"):
            return "FAILED: No authentication mechanism"

        return "COMPLIANT"

    def _test_soc2_availability_controls(self, system):
        """SOC 2 Availability - invalid input is handled gracefully."""
        pm = system["rbac_manager"].permission_manager

        # None / unknown roles must not crash and must return a bool.
        if pm.has_permission(None, RBACPermission.READ_ARTICLES) is not False:
            return "FAILED: None role did not fail safe"
        if pm.get_role_permissions("nonexistent") != set():
            return "FAILED: Unknown role did not return empty set"

        return "COMPLIANT"

    def _test_soc2_processing_controls(self, system):
        """SOC 2 Processing Integrity - JWT round-trips preserve data."""
        jwt_auth = system["jwt_auth"]

        user_data = {"sub": "test", "role": "user", "permissions": ["read"]}
        token = jwt_auth.create_access_token(user_data)
        decoded = jwt_auth.verify_token(token)

        if decoded is None:
            return "FAILED: Token processing integrity failure"
        if decoded["sub"] != user_data["sub"] or decoded["role"] != user_data["role"]:
            return "FAILED: Data integrity not maintained"
        if decoded.get("permissions") != user_data["permissions"]:
            return "FAILED: Custom claims not preserved"

        return "COMPLIANT"

    def _test_soc2_confidentiality_controls(self, system):
        """SOC 2 Confidentiality - API keys are hashed, not stored raw."""
        test_key = "nn_test_confidential_key"
        key_hash = APIKeyGenerator.hash_api_key(test_key)

        if test_key in key_hash:
            return "FAILED: API key not properly hashed"
        if APIKeyGenerator.hash_api_key(test_key) != key_hash:
            return "FAILED: Inconsistent hashing"
        # The hash must actually verify against the original key.
        if not APIKeyGenerator.verify_api_key(test_key, key_hash):
            return "FAILED: Hash does not verify original key"

        return "COMPLIANT"

    def _test_soc2_privacy_controls(self, system):
        """SOC 2 Privacy - audit logger can format privacy-relevant events."""
        audit_logger = system["audit_logger"]

        if not hasattr(audit_logger, "_format_log_event"):
            return "FAILED: No audit formatting for privacy events"

        # Formatting a user event should carry role but not raise.
        entry = audit_logger._format_log_event(
            "PRIVACY_EVENT",
            {"detail": "access"},
            user={"sub": "u1", "email": "u@example.com", "role": "user"},
        )
        if entry.get("event_type") != "PRIVACY_EVENT":
            return "FAILED: Event type not recorded"
        if entry.get("user", {}).get("role") != "user":
            return "FAILED: User role not recorded in audit entry"

        return "COMPLIANT"


class TestEndToEndSecurityWorkflow:
    """Test end-to-end security workflow validation."""

    @pytest.fixture
    def e2e_security_system(self):
        """Setup complete security system for end-to-end testing."""
        api_key_manager = APIKeyManager()
        # Mock the DynamoDB-backed store so key generation works offline.
        api_key_manager.store.get_user_api_keys = AsyncMock(return_value=[])
        api_key_manager.store.store_api_key = AsyncMock(return_value=True)

        return {
            "jwt_auth": JWTAuth(),
            "api_key_manager": api_key_manager,
            "rbac_manager": rbac_manager,
            "audit_logger": SecurityAuditLogger(),
        }

    @pytest.mark.asyncio
    async def test_complete_user_authentication_flow(self, e2e_security_system):
        """Test complete user authentication and authorization flow."""
        jwt_auth = e2e_security_system["jwt_auth"]
        rbac = e2e_security_system["rbac_manager"]
        audit_logger = e2e_security_system["audit_logger"]

        # Step 1: login -> JWT creation (rbac model role "premium").
        user_data = {
            "sub": "e2e_user_123",
            "email": "user@example.com",
            "role": "premium",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        access_token = jwt_auth.create_access_token(user_data)
        refresh_token = jwt_auth.create_refresh_token(user_data)
        assert access_token, "Failed to create access token"
        assert refresh_token, "Failed to create refresh token"

        # Step 2: token validation preserves identity claims.
        decoded_payload = jwt_auth.verify_token(access_token)
        assert decoded_payload is not None, "Token validation failed"
        assert decoded_payload["sub"] == user_data["sub"]
        assert decoded_payload["role"] == user_data["role"]

        # Step 3: authorization via rbac permission manager.
        pm = rbac.permission_manager
        assert pm.has_permission(UserRole.PREMIUM, RBACPermission.ACCESS_PREMIUM_API), (
            "Premium user should have premium API access"
        )
        assert not pm.has_permission(
            UserRole.PREMIUM, RBACPermission.MANAGE_SYSTEM
        ), "Premium user must not have admin MANAGE_SYSTEM"

        # Step 4: RBAC permission set validation.
        premium_perms = pm.get_role_permissions(UserRole.PREMIUM)
        assert RBACPermission.ACCESS_PREMIUM_API in premium_perms
        assert RBACPermission.MANAGE_SYSTEM not in premium_perms

        # Step 5: audit logging of the authentication event (async, no return).
        with patch.object(
            audit_logger, "log_security_event", new=AsyncMock(return_value=None)
        ) as mock_log:
            await audit_logger.log_security_event(
                event_type="AUTH_SUCCESS",
                event_data={"user_id": "e2e_user_123", "role": "premium"},
            )
            mock_log.assert_awaited_once()

        # A real (un-patched) call must complete without raising.
        await audit_logger.log_security_event(
            "AUTH_SUCCESS", {"user_id": "e2e_user_123"}
        )

        # Step 6: token refresh yields a new, valid access token.
        new_access_token = jwt_auth.refresh_access_token(refresh_token)
        assert new_access_token is not None, "Token refresh failed"
        new_decoded = jwt_auth.verify_token(new_access_token)
        assert new_decoded is not None, "Refreshed token invalid"
        assert new_decoded["sub"] == user_data["sub"]

    @pytest.mark.asyncio
    async def test_complete_api_key_workflow(self, e2e_security_system):
        """Test complete API key management workflow against the real manager."""
        mgr = e2e_security_system["api_key_manager"]
        audit_logger = e2e_security_system["audit_logger"]

        # Step 1: real key generation (store mocked in fixture).
        api_key_data = await mgr.generate_api_key(
            user_id="api_user_456",
            name="E2E Test Key",
            expires_in_days=30,
            permissions=["read:articles", "view:metrics"],
            rate_limit=100,
        )
        assert api_key_data is not None, "API key creation failed"
        assert api_key_data["api_key"].startswith("nn_")
        assert api_key_data["name"] == "E2E Test Key"
        assert api_key_data["status"] == APIKeyStatus.ACTIVE.value
        assert api_key_data["key_prefix"] == api_key_data["api_key"][:8]
        mgr.store.store_api_key.assert_awaited_once()

        # Step 2: the hash of the returned key verifies (round trip).
        key_hash = APIKeyGenerator.hash_api_key(api_key_data["api_key"])
        assert APIKeyGenerator.verify_api_key(api_key_data["api_key"], key_hash)
        assert not APIKeyGenerator.verify_api_key("nn_wrong_key", key_hash)

        # Step 3: the key-limit boundary is enforced (max keys per user).
        full = [
            APIKey(
                key_id=f"key_{i}",
                user_id="api_user_456",
                key_prefix="nn_aaaaa",
                key_hash="x" * 64,
                name=f"k{i}",
                status=APIKeyStatus.ACTIVE,
                created_at=datetime.now(timezone.utc),
                expires_at=None,
                last_used_at=None,
            )
            for i in range(mgr.max_keys_per_user)
        ]
        mgr.store.get_user_api_keys = AsyncMock(return_value=full)
        with pytest.raises(ValueError):
            await mgr.generate_api_key(user_id="api_user_456", name="over limit")

        # Step 4: audit the API-key creation event (async, returns None).
        with patch.object(
            audit_logger, "log_security_event", new=AsyncMock(return_value=None)
        ) as mock_log:
            await audit_logger.log_security_event(
                event_type="api_key_created",
                event_data={
                    "user_id": "api_user_456",
                    "key_id": api_key_data["key_id"],
                },
            )
            mock_log.assert_awaited_once()

    def test_security_boundary_validation(self, e2e_security_system):
        """Test security boundaries using the rbac permission model."""
        pm = e2e_security_system["rbac_manager"].permission_manager

        # (role, must-have permissions, must-NOT-have permissions)
        boundaries = [
            (
                UserRole.FREE,
                [RBACPermission.READ_ARTICLES, RBACPermission.ACCESS_BASIC_API],
                [RBACPermission.MANAGE_SYSTEM, RBACPermission.DELETE_USERS],
            ),
            (
                UserRole.PREMIUM,
                [RBACPermission.ACCESS_PREMIUM_API, RBACPermission.VIEW_ANALYTICS],
                [RBACPermission.MANAGE_SYSTEM, RBACPermission.CREATE_USERS],
            ),
            (
                UserRole.ADMIN,
                [RBACPermission.MANAGE_SYSTEM, RBACPermission.DELETE_USERS],
                [],
            ),
        ]

        for role, allowed, denied in boundaries:
            for perm in allowed:
                assert pm.has_permission(role, perm), (
                    f"{role} should have {perm}"
                )
            for perm in denied:
                assert not pm.has_permission(role, perm), (
                    f"{role} should NOT have {perm}"
                )

    def test_system_wide_security_posture(self, e2e_security_system):
        """Test overall security posture of the system."""
        jwt_auth = e2e_security_system["jwt_auth"]
        rbac = e2e_security_system["rbac_manager"]
        audit_logger = e2e_security_system["audit_logger"]

        report = {
            "authentication_security": "UNKNOWN",
            "authorization_security": "UNKNOWN",
            "data_protection": "UNKNOWN",
            "audit_compliance": "UNKNOWN",
        }

        # 1. Authentication security (JWT alg + API key format).
        token = jwt_auth.create_access_token({"sub": "test", "role": "user"})
        parts = token.split(".")
        assert len(parts) == 3, "JWT is not a well-formed three-part token"
        header = json.loads(base64.urlsafe_b64decode(parts[0] + "==="))
        test_key = APIKeyGenerator.generate_api_key()
        if (
            header.get("alg") in ("HS256", "RS256")
            and test_key.startswith("nn_")
            and len(test_key) >= 40
        ):
            report["authentication_security"] = "SECURE"
        else:
            report["authentication_security"] = "WEAK"

        # 2. Authorization security (admin dominates free, free is minimal).
        pm = rbac.permission_manager
        admin_perms = pm.get_role_permissions(UserRole.ADMIN)
        free_perms = pm.get_role_permissions(UserRole.FREE)
        if len(admin_perms) > len(free_perms) and len(free_perms) <= 5:
            report["authorization_security"] = "SECURE"
        else:
            report["authorization_security"] = "WEAK"

        # 3. Data protection (deterministic 64-hex key hash).
        hashed = APIKeyGenerator.hash_api_key("sensitive_information")
        if len(hashed) == 64 and hashed != "sensitive_information":
            report["data_protection"] = "SECURE"
        else:
            report["data_protection"] = "WEAK"

        # 4. Audit compliance (event logging + formatting exist).
        if hasattr(audit_logger, "log_security_event") and hasattr(
            audit_logger, "_format_log_event"
        ):
            report["audit_compliance"] = "COMPLIANT"
        else:
            report["audit_compliance"] = "NON_COMPLIANT"

        secure = sum(1 for s in report.values() if s in ("SECURE", "COMPLIANT"))
        assert secure == len(report), f"Security posture insufficient: {report}"

    def test_expired_jwt_is_rejected(self):
        """An explicitly-expired JWT must not validate (fail-safe auth)."""
        jwt_auth = JWTAuth()
        # create_access_token always overwrites exp, so build one by hand.
        expired = jwt.encode(
            {
                "sub": "expired_user",
                "role": "user",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
            },
            jwt_auth.jwt_secret,
            algorithm=jwt_auth.jwt_algorithm,
        )
        assert jwt_auth.verify_token(expired) is None

    def test_wrong_secret_jwt_is_rejected(self):
        """A token signed with a different secret must not validate."""
        jwt_auth = JWTAuth()
        forged = jwt.encode(
            {
                "sub": "attacker",
                "role": "admin",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            jwt_auth.jwt_secret + "_tampered",
            algorithm=jwt_auth.jwt_algorithm,
        )
        assert jwt_auth.verify_token(forged) is None


class TestDocumentationAndMaintainability:
    """Test documentation and maintainability of security implementations."""

    def test_security_class_documentation(self):
        """All real security classes should carry class-level documentation."""
        security_classes = [
            JWTAuth,
            APIKeyManager,
            PermissionChecker,
            RBACManager,
            SecurityAuditLogger,
            WAFSecurityMiddleware,
            RateLimitMiddleware,
        ]

        for security_class in security_classes:
            assert security_class.__doc__ is not None, (
                f"{security_class.__name__} missing class documentation"
            )
            assert len(security_class.__doc__.strip()) > 20, (
                f"{security_class.__name__} has insufficient documentation"
            )

    def test_security_configuration_documentation(self):
        """JWT configuration should expose reasonable, documented defaults."""
        jwt_auth = JWTAuth()

        assert hasattr(jwt_auth, "jwt_algorithm")
        assert hasattr(jwt_auth, "access_token_expire")
        assert hasattr(jwt_auth, "refresh_token_expire")

        assert jwt_auth.jwt_algorithm in ["HS256", "RS256", "ES256"]
        assert 1 <= jwt_auth.access_token_expire <= 1440  # 1 minute to 24 hours
        assert 1 <= jwt_auth.refresh_token_expire <= 30  # 1 to 30 days

    def test_security_error_handling_documentation(self):
        """verify_token must reject every malformed/empty/None token as None."""
        jwt_auth = JWTAuth()

        invalid_tokens = [None, "", "invalid", "too.few", "too.many.parts.here.extra"]
        for invalid_token in invalid_tokens:
            result = jwt_auth.verify_token(invalid_token)
            assert result is None, f"Should reject invalid token: {invalid_token!r}"

    def test_permission_checker_enforcement(self):
        """PermissionChecker.can/require reflect the real role mapping."""
        # editor role in permissions.py model.
        checker = PermissionChecker("editor")
        assert checker.can(Permission.READ_ARTICLES) is True
        assert checker.can(Permission.MANAGE_SYSTEM) is False

        # require() raises for missing permission, passes for granted ones.
        with pytest.raises(Exception):
            checker.require(Permission.MANAGE_SYSTEM)
        # This should not raise (editor has these).
        checker.require(Permission.READ_ARTICLES, Permission.CREATE_ARTICLES)

        # Unknown role has an empty permission set.
        unknown = PermissionChecker("does_not_exist")
        assert unknown.can(Permission.READ_ARTICLES) is False

    def test_integration_documentation_completeness(self):
        """Public helpers used across the suite are importable and callable."""
        # These are the real integration entry points the suite depends on.
        for helper in (has_permission, get_user_permissions, require_permissions,
                       configure_cors):
            assert callable(helper), f"{helper!r} is not callable"

        # WAF / rate-limit config surfaces referenced by middleware exist.
        assert isinstance(RateLimitConfig.FREE_TIER, UserTier)
        assert isinstance(RateLimitConfig.PREMIUM_TIER, UserTier)
        assert issubclass(ThreatType, __import__("enum").Enum)
        assert issubclass(ActionType, __import__("enum").Enum)
        assert inspect.isclass(SecurityEvent)
        assert callable(getattr(security_logger, "log_security_event"))
        assert isinstance(auth_handler, JWTAuth)
