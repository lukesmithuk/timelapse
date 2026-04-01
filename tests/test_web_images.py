from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from timelapse.config import AppConfig, LocationConfig, CameraConfig, StorageConfig
from timelapse.web.app import create_app
from timelapse.web.thumbnails import generate_thumbnail


@pytest.fixture
def app_config(tmp_path):
    storage_path = tmp_path / "timelapse"
    storage_path.mkdir()
    return AppConfig(
        location=LocationConfig(latitude=51.5, longitude=-0.1),
        cameras={"garden": CameraConfig(device=0)},
        storage=StorageConfig(path=str(storage_path), require_mount=False),
    )


@pytest.fixture
def app(app_config):
    return create_app(config=app_config)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _create_test_jpeg(path: Path) -> None:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (100, 60), color=(0, 128, 0))
    img.save(str(path), "JPEG")


class TestThumbnailGeneration:
    def test_generate_thumbnail(self, tmp_path):
        src = tmp_path / "source.jpg"
        thumb = tmp_path / "thumb.jpg"
        _create_test_jpeg(src)

        generate_thumbnail(str(src), str(thumb), width=40)

        assert thumb.exists()
        from PIL import Image
        img = Image.open(str(thumb))
        assert img.width == 40

    def test_thumbnail_preserves_aspect_ratio(self, tmp_path):
        src = tmp_path / "source.jpg"
        thumb = tmp_path / "thumb.jpg"
        _create_test_jpeg(src)  # 100x60

        generate_thumbnail(str(src), str(thumb), width=50)

        from PIL import Image
        img = Image.open(str(thumb))
        assert img.width == 50
        assert img.height == 30


class TestImageServing:
    @pytest.mark.asyncio
    async def test_serve_full_image(self, client, app_config):
        img_path = Path(app_config.storage.path) / "images" / "garden" / "2026" / "03" / "28" / "0600.jpg"
        _create_test_jpeg(img_path)

        resp = await client.get("/api/images/garden/2026/03/28/0600.jpg")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_serve_thumbnail(self, client, app_config):
        img_path = Path(app_config.storage.path) / "images" / "garden" / "2026" / "03" / "28" / "0600.jpg"
        _create_test_jpeg(img_path)

        resp = await client.get("/api/images/garden/2026/03/28/0600.jpg?thumb=1")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_missing_image_returns_404(self, client):
        resp = await client.get("/api/images/garden/2026/03/28/missing.jpg")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_path_traversal_rejected(self, client):
        """Traversal paths must not serve the target file."""
        resp = await client.get("/api/images/../../etc/passwd")
        # Should either be rejected or serve index.html (SPA fallback) — not the actual file
        assert resp.status_code in (200, 400, 404, 422)
        if resp.status_code == 200:
            assert "root:" not in resp.text  # did not serve /etc/passwd

    @pytest.mark.asyncio
    async def test_url_encoded_traversal_rejected(self, client):
        resp = await client.get("/api/images/%2e%2e/%2e%2e/etc/passwd")
        assert resp.status_code in (200, 400, 404, 422)
        if resp.status_code == 200:
            assert "root:" not in resp.text

    @pytest.mark.asyncio
    async def test_direct_traversal_in_image_path(self, client):
        """Traversal within a valid-looking path structure is caught by the regex."""
        resp = await client.get("/api/images/../../../etc/passwd")
        assert resp.status_code in (200, 400, 404, 422)
        if resp.status_code == 200:
            assert "root:" not in resp.text

    @pytest.mark.asyncio
    async def test_thumbnail_of_corrupt_image(self, client, app_config):
        img_path = Path(app_config.storage.path) / "images" / "garden" / "2026" / "03" / "28" / "bad.jpg"
        img_path.parent.mkdir(parents=True, exist_ok=True)
        img_path.write_bytes(b"not a jpeg at all")

        resp = await client.get("/api/images/garden/2026/03/28/bad.jpg?thumb=1")
        assert resp.status_code in (200, 500)
