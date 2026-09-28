"""Delil havuzu: kullanıcının verdiği ürün sayfası ve ekler.

Sunucu kullanıcı adına dış istek attığı için iç ağa (SSRF) erişim engellenmeli.
Delil toplanamazsa analiz durmamalı; eksik delil nota dönüşmeli.
"""

import os
from types import SimpleNamespace

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("USE_GCP_EMULATOR", "true")

import pytest  # noqa: E402

from api.modules import evidence_pool  # noqa: E402
from api.schemas.dossier import ProductDossier  # noqa: E402


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin",
    "http://10.0.0.5/",
    "http://169.254.169.254/computeMetadata/v1/",
    "http://localhost:8000/",
    "file:///etc/passwd",
])
def test_internal_addresses_are_refused(url):
    with pytest.raises(evidence_pool.UnsafeURLError):
        evidence_pool._check_public_host(url)


def test_redirect_to_internal_address_is_refused(monkeypatch):
    """İlk adres herkese açık olsa da yönlendirme iç ağa gidemez."""
    calls = []

    def _fake_get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(
            is_redirect=True, status_code=302, headers={"Location": "http://169.254.169.254/"},
            close=lambda: None,
        )

    monkeypatch.setattr(evidence_pool, "_check_public_host",
                        lambda url: (_ for _ in ()).throw(evidence_pool.UnsafeURLError("iç")) if "169.254" in url else None)
    monkeypatch.setattr("requests.get", _fake_get)
    with pytest.raises(evidence_pool.UnsafeURLError):
        evidence_pool.fetch_url_text("https://ornek-magaza.com/urun")
    assert calls == ["https://ornek-magaza.com/urun"]


def test_html_is_reduced_to_readable_text():
    html = """<html><head><title>Cam Balkon Sistemi</title><script>var x=1;</script></head>
    <body><nav>menü</nav><h1>Katlanır cam balkon</h1><p>Alüminyum profil, 8 mm temperli cam.</p></body></html>"""
    text = evidence_pool.html_to_text(html)
    assert "Alüminyum profil" in text and "Cam Balkon Sistemi" in text
    assert "var x" not in text and "menü" not in text


def test_unreachable_page_becomes_a_note_not_an_error(monkeypatch):
    monkeypatch.setattr(evidence_pool.settings, "USE_GCP_EMULATOR", False)
    monkeypatch.setattr(evidence_pool.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(evidence_pool, "fetch_url_text", lambda url: (_ for _ in ()).throw(TimeoutError("zaman aşımı")))
    pool = evidence_pool.collect(ProductDossier(product_name="cam balkon", product_url="https://ornek.com/urun"))
    assert pool.url_text is None
    assert any("ulaşılamadı" in note for note in pool.notes)


def test_attachments_keep_only_supported_types():
    pool = evidence_pool.collect(ProductDossier(
        product_name="cam balkon",
        attachment_uris=["gs://b/uploads/a/foto.jpg", "gs://b/uploads/a/katalog.pdf", "gs://b/uploads/a/video.mp4"],
    ))
    assert pool.attachments == [("gs://b/uploads/a/foto.jpg", "image/jpeg"), ("gs://b/uploads/a/katalog.pdf", "application/pdf")]
    assert any("video.mp4" in note for note in pool.notes)


def test_dossier_rejects_non_http_link():
    with pytest.raises(ValueError):
        ProductDossier(product_name="x ürün", product_url="javascript:alert(1)")
