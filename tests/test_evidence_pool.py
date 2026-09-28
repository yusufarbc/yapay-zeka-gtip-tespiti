"""Delil havuzu: yüklenen ekler (fotoğraf, katalog, teknik resim).

Web'den veri çekilmez; ürün sayfası linki alanı kaldırıldı. Desteklenmeyen ek
analizi durdurmaz, nota dönüşür.
"""

import os

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("USE_GCP_EMULATOR", "true")

from api.modules import evidence_pool  # noqa: E402
from api.schemas.dossier import ProductDossier  # noqa: E402


def test_attachments_keep_only_supported_types():
    pool = evidence_pool.collect(ProductDossier(
        product_name="cam balkon",
        attachment_uris=["gs://b/uploads/a/foto.jpg", "gs://b/uploads/a/katalog.pdf", "gs://b/uploads/a/video.mp4"],
    ))
    assert pool.attachments == [("gs://b/uploads/a/foto.jpg", "image/jpeg"), ("gs://b/uploads/a/katalog.pdf", "application/pdf")]
    assert any("video.mp4" in note for note in pool.notes)


def test_product_url_is_no_longer_part_of_the_dossier():
    """Eski istemciler alanı gönderse de yok sayılır; sunucu dış istek atmaz."""
    dossier = ProductDossier(product_name="cam balkon", product_url="https://ornek.com/urun")
    assert not hasattr(dossier, "product_url")
    assert not dossier.has_evidence_attachments()
    assert not hasattr(evidence_pool, "fetch_url_text")
