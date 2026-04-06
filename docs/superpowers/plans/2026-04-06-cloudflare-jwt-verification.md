# Cloudflare Access JWT Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cryptographically verify Cloudflare Access JWTs instead of trusting raw email headers, and add a new admin email.

**Architecture:** Add PyJWT dependency, extend `WebConfig` with `cf_team_name` and `cf_access_aud` fields, modify `_get_access_level()` in `app.py` to verify `Cf-Access-Jwt-Assertion` JWTs for non-local requests. JWKS keys cached on the middleware instance.

**Tech Stack:** PyJWT[crypto], httpx (existing), RS256 JWKS verification

---

### Task 1: Add PyJWT dependency

**Files:**
- Modify: `pyproject.toml:20` (web optional dependencies)

- [ ] **Step 1: Add PyJWT[crypto] to web dependencies**

In `pyproject.toml`, change the web line:

```
web = ["fastapi>=0.115", "uvicorn>=0.34", "Pillow>=11.0", "PyJWT[crypto]>=2.8"]
```

- [ ] **Step 2: Install updated dependencies**

Run: `source .venv/bin/activate && pip install -e ".[dev,web]"`
Expected: PyJWT and cryptography installed successfully

- [ ] **Step 3: Verify import works**

Run: `python -c "import jwt; print(jwt.__version__)"`
Expected: Version number printed (e.g. 2.8.0 or higher)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add PyJWT[crypto] dependency for Cloudflare JWT verification"
```

---

### Task 2: Add config fields to WebConfig

**Files:**
- Modify: `src/timelapse/config.py:125-133`
- Test: `tests/test_config.py` (existing test file — check for WebConfig tests)

- [ ] **Step 1: Write the failing test**

In `tests/test_config.py`, add:

```python
class TestWebConfig:
    def test_cf_team_name_and_aud_from_yaml(self, tmp_path, storage_dir):
        config_data = {
            "location": {"latitude": 51.5, "longitude": -0.1},
            "cameras": {"cam": {"device": 0}},
            "storage": {"path": str(storage_dir), "require_mount": False},
            "web": {
                "admin_emails": ["a@b.com"],
                "cf_team_name": "myteam",
                "cf_access_aud": "abc123",
            },
        }
        path = tmp_path / "cfg.yaml"
        import yaml
        path.write_text(yaml.dump(config_data))
        from timelapse.config import load_config
        cfg = load_config(path)
        assert cfg.web.cf_team_name == "myteam"
        assert cfg.web.cf_access_aud == "abc123"

    def test_cf_fields_default_to_none(self, tmp_path, storage_dir):
        config_data = {
            "location": {"latitude": 51.5, "longitude": -0.1},
            "cameras": {"cam": {"device": 0}},
            "storage": {"path": str(storage_dir), "require_mount": False},
        }
        path = tmp_path / "cfg.yaml"
        import yaml
        path.write_text(yaml.dump(config_data))
        from timelapse.config import load_config
        cfg = load_config(path)
        assert cfg.web.cf_team_name is None
        assert cfg.web.cf_access_aud is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::TestWebConfig -v`
Expected: FAIL with `AttributeError: 'WebConfig' object has no attribute 'cf_team_name'`

- [ ] **Step 3: Add fields to WebConfig**

In `src/timelapse/config.py`, replace the `WebConfig` dataclass (lines 125-132):

```python
@dataclass
class WebConfig:
    admin_emails: list[str] = field(default_factory=list)
    domain: Optional[str] = None  # e.g. "garden.example.com" for CORS
    cf_team_name: Optional[str] = None  # Cloudflare Access team name
    cf_access_aud: Optional[str] = None  # Cloudflare Access Application Audience tag

    def __post_init__(self) -> None:
        if isinstance(self.admin_emails, str):
            self.admin_emails = [self.admin_emails]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py::TestWebConfig -v`
Expected: PASS

- [ ] **Step 5: Run all config tests to check nothing broke**

Run: `pytest tests/test_config.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/timelapse/config.py tests/test_config.py
git commit -m "feat: add cf_team_name and cf_access_aud to WebConfig"
```

---

### Task 3: Implement JWT verification in middleware

**Files:**
- Modify: `src/timelapse/web/app.py:1-82`
- Test: `tests/test_web_access.py`

- [ ] **Step 1: Write test fixtures for JWT verification**

Add these imports and fixtures at the top of `tests/test_web_access.py`:

```python
import json
import time
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from unittest.mock import patch, AsyncMock
```

Add a module-level RSA keypair and helper after the existing imports:

```python
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
```

- [ ] **Step 2: Write failing test for JWT admin access**

Add a new test class in `tests/test_web_access.py`:

```python
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
        """Local network requests don't need JWT — still get local access."""
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_web_access.py::TestJWTVerification -v`
Expected: FAIL (multiple failures — `_fetch_jwks` doesn't exist, JWT not being verified)

- [ ] **Step 4: Implement JWT verification in app.py**

In `src/timelapse/web/app.py`, add imports after the existing ones:

```python
import logging
import jwt as pyjwt
from jwt.algorithms import RSAAlgorithm

logger = logging.getLogger(__name__)
```

Add a JWKS fetch and cache function after `_PRIVATE_NETS`:

```python
# JWKS cache: {team_name: {"keys": {...}, "fetched_at": float}}
_jwks_cache: dict[str, dict] = {}


def _fetch_jwks(team_name: str) -> dict:
    """Fetch JWKS from Cloudflare Access. Results are cached in memory."""
    import time
    cache_entry = _jwks_cache.get(team_name)
    if cache_entry and (time.time() - cache_entry["fetched_at"]) < 3600:
        return cache_entry["keys"]

    import httpx
    url = f"https://{team_name}.cloudflareaccess.com/cdn-cgi/access/certs"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    keys = resp.json()
    _jwks_cache[team_name] = {"keys": keys, "fetched_at": time.time()}
    return keys


def _verify_cf_jwt(token: str, team_name: str, aud: Optional[str] = None) -> Optional[str]:
    """Verify a Cloudflare Access JWT and return the email, or None on failure."""
    try:
        jwks = _fetch_jwks(team_name)
        # Get the signing key from JWKS
        unverified_header = pyjwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        key_data = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                key_data = key
                break

        if key_data is None:
            # Key not found — try refreshing the cache
            _jwks_cache.pop(team_name, None)
            jwks = _fetch_jwks(team_name)
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    key_data = key
                    break

        if key_data is None:
            logger.warning("JWT kid %s not found in JWKS", kid)
            return None

        public_key = RSAAlgorithm.from_jwk(key_data)
        decode_options = {
            "algorithms": ["RS256"],
            "issuer": f"https://{team_name}.cloudflareaccess.com",
        }
        if aud:
            decode_options["audience"] = aud
        else:
            decode_options["options"] = {"verify_aud": False}

        payload = pyjwt.decode(token, public_key, **decode_options)
        return payload.get("email")
    except Exception as e:
        logger.warning("JWT verification failed: %s", e)
        return None
```

Replace `_get_access_level` (lines 49-82) with:

```python
def _get_access_level(request: Request) -> str:
    """Determine access level: 'admin', 'viewer', or 'local'.

    - local: request from private network (full access)
    - admin: verified Cloudflare Access JWT with email in admin_emails list
    - viewer: all other external requests

    When behind Cloudflare Tunnel, cloudflared forwards requests to localhost,
    so request.client.host is always 127.0.0.1. We use Cf-Connecting-IP
    (the real client IP set by Cloudflare) to distinguish local from external.
    If Cf-Connecting-IP is absent, the request came directly (not via tunnel)
    and we use the TCP peer address.
    """
    # Use Cloudflare's real client IP if present (tunnel traffic)
    cf_ip = request.headers.get("Cf-Connecting-IP")
    if cf_ip:
        client_ip = cf_ip
    else:
        client_ip = request.client.host if request.client else "0.0.0.0"

    # Local network = full access
    if _is_local(client_ip):
        return "local"

    # Verify Cloudflare Access JWT for non-local requests
    web_config = request.app.state.config.web
    cf_token = request.headers.get("Cf-Access-Jwt-Assertion", "")
    if cf_token and web_config.cf_team_name:
        email = _verify_cf_jwt(cf_token, web_config.cf_team_name, web_config.cf_access_aud)
        if email and email.lower() in [e.lower() for e in web_config.admin_emails]:
            return "admin"

    return "viewer"
```

- [ ] **Step 5: Run JWT tests to verify they pass**

Run: `pytest tests/test_web_access.py::TestJWTVerification -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/timelapse/web/app.py tests/test_web_access.py
git commit -m "feat: verify Cloudflare Access JWT for admin authentication"
```

---

### Task 4: Update existing tests for JWT-based auth

**Files:**
- Modify: `tests/test_web_access.py`

The existing `TestViewerRestrictions` tests that use `Cf-Access-Authenticated-User-Email` need updating since the middleware no longer reads that header. The admin test now needs a valid JWT.

- [ ] **Step 1: Update the admin POST test**

In `tests/test_web_access.py`, update `TestViewerRestrictions.test_admin_email_can_post_renders`:

```python
    @pytest.mark.asyncio
    async def test_admin_email_can_post_renders(self, client, db):
        """Without JWT config, raw email header is ignored — admin needs JWT."""
        # This app_config has no cf_team_name, so JWT verification is skipped
        # and all external requests are viewers. This tests graceful degradation.
        headers = {**self.EXTERNAL_HEADERS, "Cf-Access-Authenticated-User-Email": "admin@example.com"}
        resp = await client.post("/api/renders",
            json={"camera": "garden", "date_from": "2026-03-01", "date_to": "2026-03-28"},
            headers=headers,
        )
        assert resp.status_code == 403
```

Update `test_non_admin_email_blocked_from_post` to reflect that raw email headers are now always ignored:

```python
    @pytest.mark.asyncio
    async def test_raw_email_header_ignored_without_jwt(self, client):
        """Raw Cf-Access-Authenticated-User-Email header is no longer trusted."""
        headers = {**self.EXTERNAL_HEADERS, "Cf-Access-Authenticated-User-Email": "friend@example.com"}
        resp = await client.post("/api/renders",
            json={"camera": "garden", "date_from": "2026-03-01", "date_to": "2026-03-28"},
            headers=headers,
        )
        assert resp.status_code == 403
```

- [ ] **Step 2: Run updated tests**

Run: `pytest tests/test_web_access.py::TestViewerRestrictions -v`
Expected: All PASS

- [ ] **Step 3: Run the full access test suite**

Run: `pytest tests/test_web_access.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_web_access.py
git commit -m "test: update access tests for JWT-based auth (raw header no longer trusted)"
```

---

### Task 5: Test JWKS cache refresh on key rotation

**Files:**
- Modify: `tests/test_web_access.py`

- [ ] **Step 1: Write the key rotation test**

Add to `TestJWTVerification` in `tests/test_web_access.py`:

```python
    @pytest.mark.asyncio
    async def test_jwks_cache_refresh_on_unknown_kid(self, jwt_client):
        """When JWT has an unknown kid, middleware re-fetches JWKS."""
        # First call returns empty keys, second call returns the real keys
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
        assert call_count == 2  # Initial fetch + retry after kid miss
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_web_access.py::TestJWTVerification::test_jwks_cache_refresh_on_unknown_kid -v`
Expected: PASS (the retry logic in `_verify_cf_jwt` already handles this)

- [ ] **Step 3: Commit**

```bash
git add tests/test_web_access.py
git commit -m "test: verify JWKS cache refresh on key rotation"
```

---

### Task 6: Test no cf_team_name configured (graceful degradation)

**Files:**
- Modify: `tests/test_web_access.py`

- [ ] **Step 1: Write the degradation test**

Add to `TestJWTVerification` in `tests/test_web_access.py`:

```python
    @pytest.mark.asyncio
    async def test_no_team_name_all_external_are_viewers(self, app_config):
        """Without cf_team_name, JWT verification is skipped — all external = viewer."""
        # app_config fixture has no cf_team_name
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
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_web_access.py::TestJWTVerification::test_no_team_name_all_external_are_viewers -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_web_access.py
git commit -m "test: verify graceful degradation without cf_team_name"
```

---

### Task 7: Update config files and example YAML

**Files:**
- Modify: `timelapse.example.yaml`
- Modify: `/etc/timelapse/timelapse.yaml` (production — manual deploy)

- [ ] **Step 1: Update the example YAML**

In `timelapse.example.yaml`, replace the `web:` section:

```yaml
# Web UI access control (for Cloudflare Access)
# Admin emails get full access (including render) from external network
# All other authenticated users get view-only access
# Local network always has full access
web:
  domain: garden.example.com  # Your Cloudflare Tunnel subdomain (for CORS)
  cf_team_name: your-team     # Cloudflare Access team name (from Zero Trust dashboard)
  cf_access_aud: null          # Optional: Application Audience tag (from Access app config)
  admin_emails:
    - admin@example.com
```

- [ ] **Step 2: Update the production config**

In `/etc/timelapse/timelapse.yaml`, update the `web:` section:

```yaml
web:
  domain: garden.lukesmith.com
  cf_team_name: lukesmithuk
  admin_emails:
    - luke@lukesmith.com
    - dee.pandya314@gmail.com
```

Note: `cf_access_aud` is omitted (defaults to None — audience validation skipped). Can be added later by finding the Application Audience tag in the Cloudflare Zero Trust dashboard under Access > Applications > your app > Overview.

- [ ] **Step 3: Commit the example YAML (not the production config)**

```bash
git add timelapse.example.yaml
git commit -m "docs: add cf_team_name and cf_access_aud to example config"
```

---

### Task 8: Update CLAUDE.md and run full test suite

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md TODO section**

Remove the JWT verification TODO from the list since it's now implemented. The TODO section should now read:

```markdown
## TODO

- Create a dedicated `timelapse` service account instead of running systemd services as user `pls`
- **AI Hat+ integration**: Use the Raspberry Pi AI Hat to assess weather conditions in images and tag if people are present
```

- [ ] **Step 2: Add JWT pattern to Key Patterns section**

Add to the Key Patterns section in `CLAUDE.md`:

```markdown
- **Cloudflare JWT verification**: `_verify_cf_jwt()` in `app.py` validates `Cf-Access-Jwt-Assertion` using Cloudflare's JWKS. Keys cached in `_jwks_cache` with 1-hour TTL and retry on unknown `kid`. Requires `cf_team_name` in web config; without it, all external requests are viewers.
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for JWT verification"
```

---

### Task 9: Deploy and verify

- [ ] **Step 1: Rebuild and restart**

```bash
cd frontend && npm run build && cd ..
sudo systemctl restart timelapse.target
```

- [ ] **Step 2: Verify services are running**

Run: `systemctl is-active timelapse.target timelapse-capture timelapse-render timelapse-web`
Expected: All `active`

- [ ] **Step 3: Verify local access still works**

Run: `curl -s http://localhost:8080/api/status | python3 -m json.tool | grep access`
Expected: `"access": "local"`

- [ ] **Step 4: Verify external access without JWT is viewer**

Run: `curl -s -H "Cf-Connecting-IP: 8.8.8.8" http://localhost:8080/api/status | python3 -m json.tool | grep access`
Expected: `"access": "viewer"`
