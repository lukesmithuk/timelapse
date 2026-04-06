# Cloudflare Access JWT Verification

## Problem

The `AccessMiddleware` trusts the `Cf-Access-Authenticated-User-Email` header without cryptographic verification. Anyone on the local network can spoof this header by sending requests directly to port 8080, bypassing Cloudflare and gaining admin access.

## Solution

Verify the `Cf-Access-Jwt-Assertion` JWT on non-local requests using Cloudflare's public signing keys. Extract the email from the verified token payload instead of trusting the raw header.

## Scope

- JWT verification in `AccessMiddleware`
- New `cf_team_name` config field
- Add `dee.pandya314@gmail.com` as admin
- New dependency: `PyJWT[crypto]`
- Updated tests

## Config Changes

Add `cf_team_name` to `WebConfig`:

```python
@dataclass
class WebConfig:
    admin_emails: list[str] = field(default_factory=list)
    domain: Optional[str] = None
    cf_team_name: Optional[str] = None  # Required when admin_emails is non-empty
```

Example YAML:

```yaml
web:
  domain: garden.lukesmith.com
  cf_team_name: lukesmithuk
  admin_emails:
    - luke@lukesmith.com
    - dee.pandya314@gmail.com
```

## Middleware Changes

### Current flow (non-local requests)

1. Read `Cf-Access-Authenticated-User-Email` header
2. Match against `admin_emails` list
3. Return "admin" or "viewer"

### New flow (non-local requests)

1. Read `Cf-Access-Jwt-Assertion` header
2. If missing or `cf_team_name` not configured: return "viewer"
3. Fetch JWKS from `https://{cf_team_name}.cloudflareaccess.com/cdn-cgi/access/certs`
4. Verify JWT signature (RS256) against the public keys
5. Validate `iss` claim matches `https://{cf_team_name}.cloudflareaccess.com`
6. Validate `aud` claim (use the Application Audience tag from Cloudflare Access config)
7. Extract `email` from payload
8. Match against `admin_emails` (case-insensitive)
9. Return "admin" or "viewer"
10. On any verification failure: return "viewer"

### Local requests

No change. Local network requests skip JWT verification entirely.

### `Cf-Access-Authenticated-User-Email` header

No longer read. The JWT `email` claim is the sole source of truth for admin identification.

## Key Caching

- JWKS fetched once and cached on the middleware instance
- On verification failure with unknown `kid`: re-fetch JWKS once and retry
- Use `httpx` (already a dependency) for the HTTP fetch
- Synchronous fetch is acceptable here since it only happens at startup and on key rotation

## Audience Tag

Cloudflare Access assigns an Application Audience (AUD) tag to each Access application. This must be validated in the JWT to prevent tokens from one Cloudflare Access app being used against another. Add `cf_access_aud` to `WebConfig`:

```python
cf_access_aud: Optional[str] = None  # Application Audience tag
```

If not configured, skip audience validation (graceful degradation).

## New Dependency

`PyJWT[crypto]` in `pyproject.toml` under the `web` extra (alongside `fastapi`, `uvicorn`, etc.). This pulls in `cryptography` for RS256 support.

## Error Handling

All JWT verification failures (expired, bad signature, missing claims, fetch failures) result in "viewer" access. No 401s, no broken pages. This matches the existing graceful degradation pattern (similar to how MQTT failures are handled).

Verification errors are logged at WARNING level for debugging.

## Testing

- Generate a test RS256 keypair in `conftest.py`
- Mock the JWKS endpoint response (no real HTTP calls in tests)
- Test cases:
  - Valid JWT with admin email -> "admin" access
  - Valid JWT with non-admin email -> "viewer" access
  - Missing JWT header from external IP -> "viewer" access
  - Invalid/expired JWT -> "viewer" access
  - Local network requests -> "local" access (JWT ignored)
  - Key rotation: unknown `kid` triggers JWKS re-fetch
  - `cf_team_name` not configured -> "viewer" for all external requests
