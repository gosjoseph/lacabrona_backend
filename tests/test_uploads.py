"""Tests for the /api/v1/uploads/image endpoint and its image stores.

Covers both the local (DEV) and Cloudinary (PROD) stores plus the
environment-driven selector. No network: the Cloudinary uploader is patched.
"""

from __future__ import annotations

import io
import os

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.modules.uploads import service as uploads_service
from app.modules.uploads.controller import router as uploads_router  # noqa: F401  # ensures import
from app.modules.uploads.service import (
    CloudinaryImageStore,
    LocalImageStore,
    get_image_store,
)


# ---- Store unit tests ------------------------------------------------------


def test_local_store_writes_file_and_returns_url(tmp_path):
    store = LocalImageStore(str(tmp_path), "http://localhost:8000")
    out = store.save(b"binarydata", "image/png")

    assert out["url"].startswith("http://localhost:8000/media/menu/")
    assert out["url"].endswith(".png")
    assert out["ref"].startswith("menu/")
    # the file actually exists in tmp_path/menu/
    rel = out["ref"]  # "menu/<uuid>.png"
    assert (tmp_path / rel).exists()


def test_cloudinary_store_saves_and_calls_uploader(monkeypatch):
    monkeypatch.setattr(settings, "cloudinary_cloud_name", "demo")
    monkeypatch.setattr(settings, "cloudinary_api_key", "key")
    monkeypatch.setattr(settings, "cloudinary_api_secret", "secret")

    calls = {}

    def fake_upload(payload, **kwargs):
        calls["payload"] = payload
        calls["kwargs"] = kwargs
        return {
            "secure_url": "https://res.cloudinary.com/x/.../lacabrona/menu/abc.jpg",
            "public_id": "lacabrona/menu/abc",
        }

    monkeypatch.setattr(uploads_service.cloudinary.uploader, "upload", fake_upload)

    out = CloudinaryImageStore().save(b"binarydata", "image/jpeg")

    assert out == {
        "url": "https://res.cloudinary.com/x/.../lacabrona/menu/abc.jpg",
        "ref": "lacabrona/menu/abc",
    }
    assert calls["kwargs"].get("folder") == "lacabrona/menu"
    assert calls["kwargs"].get("resource_type") == "image"


def test_cloudinary_store_not_configured_raises_503(monkeypatch):
    monkeypatch.setattr(settings, "cloudinary_cloud_name", "")

    with pytest.raises(HTTPException) as exc:
        CloudinaryImageStore()
    assert exc.value.status_code == 503


def test_cloudinary_store_uploader_error_raises_502(monkeypatch):
    monkeypatch.setattr(settings, "cloudinary_cloud_name", "demo")
    monkeypatch.setattr(settings, "cloudinary_api_key", "key")
    monkeypatch.setattr(settings, "cloudinary_api_secret", "secret")

    def boom(*args, **kwargs):
        raise RuntimeError("cloudinary network down")

    monkeypatch.setattr(uploads_service.cloudinary.uploader, "upload", boom)

    with pytest.raises(HTTPException) as exc:
        CloudinaryImageStore().save(b"x", "image/png")
    assert exc.value.status_code == 502


# ---- Selector tests --------------------------------------------------------


def test_selector_picks_cloudinary_in_prod(monkeypatch):
    monkeypatch.setattr(settings, "environment", "prod")
    monkeypatch.setattr(settings, "cloudinary_cloud_name", "demo")
    monkeypatch.setattr(settings, "cloudinary_api_key", "key")
    monkeypatch.setattr(settings, "cloudinary_api_secret", "secret")

    store = get_image_store()
    assert isinstance(store, CloudinaryImageStore)


def test_selector_picks_local_in_dev(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "environment", "dev")
    monkeypatch.setattr(settings, "media_dir", str(tmp_path))
    monkeypatch.setattr(settings, "media_base_url", "http://localhost:8000")

    store = get_image_store()
    assert isinstance(store, LocalImageStore)


# ---- Endpoint tests --------------------------------------------------------


@pytest.fixture
def upload_client(tmp_path):
    """A TestClient with get_image_store overridden to a LocalImageStore.

    Uploads are gated behind an employee session, so authenticate as one.
    """
    import mongomock

    from tests.conftest import employee_auth_overrides

    store = LocalImageStore(str(tmp_path), "http://t")
    auth_db = mongomock.MongoClient()["lacabrona_uploads_test"]

    overrides = {get_image_store: lambda: store}
    overrides.update(employee_auth_overrides(auth_db))

    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app) as client:
            yield client, tmp_path
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)


def test_upload_image_png_returns_url(upload_client):
    client, tmp_path = upload_client
    files = {"file": ("a.png", io.BytesIO(b"\x89PNG\r\n\x1a\nbinary"), "image/png")}
    response = client.post("/api/v1/uploads/image", files=files)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["url"].startswith("http://t/media/menu/")
    assert body["url"].endswith(".png")
    assert body["ref"].startswith("menu/")


def test_upload_image_rejects_non_image(upload_client):
    client, tmp_path = upload_client
    files = {"file": ("a.txt", io.BytesIO(b"hello"), "text/plain")}
    response = client.post("/api/v1/uploads/image", files=files)

    assert response.status_code == 400
    # nothing should have been written into the menu/ dir
    menu_dir = tmp_path / "menu"
    assert not any(menu_dir.iterdir())


def test_upload_image_rejects_oversize(upload_client):
    client, _ = upload_client
    payload = b"x" * (5 * 1024 * 1024 + 1)
    files = {"file": ("big.png", io.BytesIO(payload), "image/png")}
    response = client.post("/api/v1/uploads/image", files=files)

    assert response.status_code == 400


def test_openapi_exposes_uploads_image():
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/v1/uploads/image" in response.json()["paths"]
