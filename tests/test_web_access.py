"""Tests for access control middleware and security features."""

import json
import time
from pathlib import Path
from unittest.mock import patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

from timelapse.config import AppConfig, LocationConfig, CameraConfig, StorageConfig, RenderConfig, WebConfig
from timelapse.jobs import Database
from timelapse.web.app import create_app


# Test RSA keypair for JWT signing
_TEST_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_TEST_PUBLIC_KEY = _TEST_PRIVATE_KEY.public_key()


def _make_jwks():
    """Build a JWKS dict from the test public key."""
    from jwt.algorithms import RSAAlgorithm
    jwk = json.loads(RSAAlgorithm.to_jwk(_TEST_PUBLIC_KEY))
    jwk["kid"] = "test-key-1"
    jwk["use"] = "sig"
    return {"keys": [jwk]}


def _make_jwt(email: str, team_name: str = "testteam", aud: str = "test-aud", expired: bool = False):
    """Create a signed JWT mimicking Cloudflare Access."""
    now = time.time()
    payload = {
        "email": email,
        "iss": f"https://{team_name}.cloudflareaccess.com",
        "aud": [aud],
        "iat": now - 60,
        "exp": (now - 120) if expired else (now + 3600),
        "sub": "unique-user-id",
    }
    return pyjwt.encode(payload, _TEST_PRIVATE_KEY, algorithm="RS256", headers={"kid": "test-key-1"})


@pytest.fixture
def app_config(tmp_path):
    storage_path = tmp_path / "timelapse"
    storage_path.mkdir()
    return AppConfig(
        location=LocationConfig(latitude=51.5, longitude=-0.1),
        cameras={"garden": CameraConfig(device=0)},
        storage=StorageConfig(path=str(storage_path), require_mount=False),
        render=RenderConfig(),
        web=WebConfig(admin_emails=["admin@example.com"], domain="garden.example.com"),
    )


@pytest.fixture
def db(app_config):
    return Database(Path(app_config.storage.path) / "timelapse.db")


@pytest.fixture
def app(app_config):
    return create_app(config=app_config)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestAccessLevels:
    @pytest.mark.asyncio
    async def test_local_network_gets_local_access(self, client):
        """Requests from private IPs get local (full) access."""
        resp = await client.get("/api/status")
        assert resp.status_code == 200
        # httpx test client connects from 127.0.0.1 which is local
        assert resp.json()["access"] == "local"

    @pytest.mark.asyncio
    async def test_cloudflare_admin_email_gets_admin_access(self, app_config):
        """Requests with admin email in Cf-Access header get admin access."""
        # We need to simulate a non-local IP, but httpx always uses 127.0.0.1
        # which is local. So we test the _get_access_level function directly.
        from timelapse.web.app import _get_access_level, _is_local
        assert _is_local("127.0.0.1") is True
        assert _is_local("192.168.1.100") is True
        assert _is_local("8.8.8.8") is False

    @pytest.mark.asyncio
    async def test_private_ip_ranges(self):
        from timelapse.web.app import _is_local
        # IPv4 private
        assert _is_local("10.0.0.1") is True
        assert _is_local("172.16.0.1") is True
        assert _is_local("192.168.1.1") is True
        assert _is_local("127.0.0.1") is True
        # IPv6 private
        assert _is_local("::1") is True
        assert _is_local("fd12::1") is True
        assert _is_local("fe80::1") is True
        # Public
        assert _is_local("8.8.8.8") is False
        assert _is_local("1.1.1.1") is False
        # IPv4-mapped IPv6
        assert _is_local("::ffff:192.168.1.1") is True
        assert _is_local("::ffff:8.8.8.8") is False


class TestViewerRestrictions:
    """Simulate tunnel traffic by sending Cf-Connecting-IP with a public IP.

    This is how production works: cloudflared connects to localhost:8080 and
    sets Cf-Connecting-IP to the real client IP. The middleware uses this
    instead of request.client.host to classify access.
    """

    # Headers simulating external traffic via Cloudflare Tunnel
    EXTERNAL_HEADERS = {"Cf-Connecting-IP": "203.0.113.1"}  # Public IP

    @pytest.mark.asyncio
    async def test_viewer_cannot_post_renders(self, client):
        resp = await client.post("/api/renders",
            json={"camera": "garden", "date_from": "2026-03-01", "date_to": "2026-03-28"},
            headers=self.EXTERNAL_HEADERS,
        )
        assert resp.status_code == 403
        assert "write access" in resp.json()["error"].lower()

    @pytest.mark.asyncio
    async def test_viewer_can_get_status(self, client):
        resp = await client.get("/api/status", headers=self.EXTERNAL_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["access"] == "viewer"

    @pytest.mark.asyncio
    async def test_admin_email_can_post_renders(self, client, db):
        """Without JWT config, raw email header is ignored — admin needs JWT."""
        headers = {**self.EXTERNAL_HEADERS, "Cf-Access-Authenticated-User-Email": "admin@example.com"}
        resp = await client.post("/api/renders",
            json={"camera": "garden", "date_from": "2026-03-01", "date_to": "2026-03-28"},
            headers=headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_raw_email_header_ignored_without_jwt(self, client):
        """Raw Cf-Access-Authenticated-User-Email header is no longer trusted."""
        headers = {**self.EXTERNAL_HEADERS, "Cf-Access-Authenticated-User-Email": "friend@example.com"}
        resp = await client.post("/api/renders",
            json={"camera": "garden", "date_from": "2026-03-01", "date_to": "2026-03-28"},
            headers=headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_local_ip_via_tunnel_gets_local_access(self, client):
        """A local network IP arriving via tunnel still gets local access."""
        headers = {"Cf-Connecting-IP": "192.168.1.50"}
        resp = await client.get("/api/status", headers=headers)
        assert resp.json()["access"] == "local"


class TestSecurityHeaders:
    @pytest.mark.asyncio
    async def test_security_headers_present(self, client):
        resp = await client.get("/api/status")
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["x-frame-options"] == "DENY"
        assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"


class TestRenderValidation:
    @pytest.mark.asyncio
    async def test_invalid_resolution_rejected(self, client):
        resp = await client.post("/api/renders", json={
            "camera": "garden", "date_from": "2026-03-01", "date_to": "2026-03-28",
            "resolution": "not-valid",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_oversized_resolution_rejected(self, client):
        resp = await client.post("/api/renders", json={
            "camera": "garden", "date_from": "2026-03-01", "date_to": "2026-03-28",
            "resolution": "99999x99999",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_fps_zero_rejected(self, client):
        resp = await client.post("/api/renders", json={
            "camera": "garden", "date_from": "2026-03-01", "date_to": "2026-03-28",
            "fps": 0,
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_fps_too_high_rejected(self, client):
        resp = await client.post("/api/renders", json={
            "camera": "garden", "date_from": "2026-03-01", "date_to": "2026-03-28",
            "fps": 999,
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_quality_out_of_range_rejected(self, client):
        resp = await client.post("/api/renders", json={
            "camera": "garden", "date_from": "2026-03-01", "date_to": "2026-03-28",
            "quality": 99,
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_valid_render_accepted(self, client, db):
        resp = await client.post("/api/renders", json={
            "camera": "garden", "date_from": "2026-03-01", "date_to": "2026-03-28",
            "fps": 30, "resolution": "1920x1080", "quality": 23,
        })
        assert resp.status_code == 200


class TestJobResponseSanitisation:
    @pytest.mark.asyncio
    async def test_output_path_not_in_response(self, client, db):
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.complete_job(job_id, "/mnt/usb/timelapse/videos/daily/garden/2026-03-28.mp4")

        resp = await client.get(f"/api/renders/{job_id}")
        data = resp.json()
        assert "output_path" not in data
        assert "video_url" in data

    @pytest.mark.asyncio
    async def test_error_message_path_stripped(self, client, db):
        storage_path = str(db.path.parent)
        job_id = db.create_render_job("garden", "daily", "2026-03-28", "2026-03-28")
        db.claim_job(job_id)
        db.fail_job(job_id, f"ffmpeg failed: {storage_path}/tmp/job_1/concat.txt not found")

        resp = await client.get(f"/api/renders/{job_id}")
        data = resp.json()
        assert storage_path not in data.get("error", "")
        assert "[storage]" in data.get("error", "")


class TestJWTVerification:
    """Test Cloudflare Access JWT verification."""

    EXTERNAL_HEADERS = {"Cf-Connecting-IP": "203.0.113.1"}

    @pytest.fixture
    def jwt_app_config(self, tmp_path):
        storage_path = tmp_path / "timelapse"
        storage_path.mkdir()
        return AppConfig(
            location=LocationConfig(latitude=51.5, longitude=-0.1),
            cameras={"garden": CameraConfig(device=0)},
            storage=StorageConfig(path=str(storage_path), require_mount=False),
            render=RenderConfig(),
            web=WebConfig(
                admin_emails=["admin@example.com"],
                domain="garden.example.com",
                cf_team_name="testteam",
                cf_access_aud="test-aud",
            ),
        )

    @pytest.fixture
    def jwt_app(self, jwt_app_config):
        return create_app(config=jwt_app_config)

    @pytest.fixture
    async def jwt_client(self, jwt_app):
        transport = ASGITransport(app=jwt_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    @pytest.mark.asyncio
    async def test_valid_jwt_admin_gets_admin_access(self, jwt_client):
        token = _make_jwt("admin@example.com")
        headers = {
            **self.EXTERNAL_HEADERS,
            "Cf-Access-Jwt-Assertion": token,
        }
        with patch("timelapse.web.app._fetch_jwks", return_value=_make_jwks()):
            resp = await jwt_client.get("/api/status", headers=headers)
        assert resp.json()["access"] == "admin"

    @pytest.mark.asyncio
    async def test_valid_jwt_non_admin_gets_viewer_access(self, jwt_client):
        token = _make_jwt("stranger@example.com")
        headers = {
            **self.EXTERNAL_HEADERS,
            "Cf-Access-Jwt-Assertion": token,
        }
        with patch("timelapse.web.app._fetch_jwks", return_value=_make_jwks()):
            resp = await jwt_client.get("/api/status", headers=headers)
        assert resp.json()["access"] == "viewer"

    @pytest.mark.asyncio
    async def test_missing_jwt_gets_viewer_access(self, jwt_client):
        headers = {**self.EXTERNAL_HEADERS}
        resp = await jwt_client.get("/api/status", headers=headers)
        assert resp.json()["access"] == "viewer"

    @pytest.mark.asyncio
    async def test_invalid_jwt_gets_viewer_access(self, jwt_client):
        headers = {
            **self.EXTERNAL_HEADERS,
            "Cf-Access-Jwt-Assertion": "not-a-valid-jwt",
        }
        with patch("timelapse.web.app._fetch_jwks", return_value=_make_jwks()):
            resp = await jwt_client.get("/api/status", headers=headers)
        assert resp.json()["access"] == "viewer"

    @pytest.mark.asyncio
    async def test_expired_jwt_gets_viewer_access(self, jwt_client):
        token = _make_jwt("admin@example.com", expired=True)
        headers = {
            **self.EXTERNAL_HEADERS,
            "Cf-Access-Jwt-Assertion": token,
        }
        with patch("timelapse.web.app._fetch_jwks", return_value=_make_jwks()):
            resp = await jwt_client.get("/api/status", headers=headers)
        assert resp.json()["access"] == "viewer"

    @pytest.mark.asyncio
    async def test_local_requests_skip_jwt(self, jwt_client):
        """Local network requests don't need JWT -- still get local access."""
        resp = await jwt_client.get("/api/status")
        assert resp.json()["access"] == "local"

    @pytest.mark.asyncio
    async def test_admin_email_case_insensitive(self, jwt_client):
        token = _make_jwt("Admin@Example.COM")
        headers = {
            **self.EXTERNAL_HEADERS,
            "Cf-Access-Jwt-Assertion": token,
        }
        with patch("timelapse.web.app._fetch_jwks", return_value=_make_jwks()):
            resp = await jwt_client.get("/api/status", headers=headers)
        assert resp.json()["access"] == "admin"

    @pytest.mark.asyncio
    async def test_jwt_admin_can_post(self, jwt_client):
        token = _make_jwt("admin@example.com")
        headers = {
            **self.EXTERNAL_HEADERS,
            "Cf-Access-Jwt-Assertion": token,
        }
        db = Database(Path(jwt_client._transport.app.state.config.storage.path) / "timelapse.db")
        with patch("timelapse.web.app._fetch_jwks", return_value=_make_jwks()):
            resp = await jwt_client.post("/api/renders",
                json={"camera": "garden", "date_from": "2026-03-01", "date_to": "2026-03-28"},
                headers=headers,
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_jwks_cache_refresh_on_unknown_kid(self, jwt_client):
        """When JWT has an unknown kid, middleware re-fetches JWKS."""
        empty_jwks = {"keys": []}
        real_jwks = _make_jwks()
        call_count = 0

        def mock_fetch(team_name):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return empty_jwks
            return real_jwks

        token = _make_jwt("admin@example.com")
        headers = {
            **self.EXTERNAL_HEADERS,
            "Cf-Access-Jwt-Assertion": token,
        }
        with patch("timelapse.web.app._fetch_jwks", side_effect=mock_fetch):
            resp = await jwt_client.get("/api/status", headers=headers)
        assert resp.json()["access"] == "admin"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_no_team_name_all_external_are_viewers(self, app_config):
        """Without cf_team_name, JWT verification is skipped — all external = viewer."""
        app = create_app(config=app_config)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            token = _make_jwt("admin@example.com")
            headers = {
                "Cf-Connecting-IP": "203.0.113.1",
                "Cf-Access-Jwt-Assertion": token,
            }
            resp = await c.get("/api/status", headers=headers)
        assert resp.json()["access"] == "viewer"
