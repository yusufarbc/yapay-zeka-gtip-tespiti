"""Ürün dosyasındaki delilleri tek havuzda toplar.

Genel web araması YAPILMAZ: canlı arama ölçümde ~25 sn sürüp çoğunlukla 504 ile
boş dönüyordu. Yalnız kullanıcının verdiği ürün sayfası çekilir. Ekler (fotoğraf,
katalog, teknik resim) modele doğrudan GCS URI'siyle verilir.

Delil toplanamazsa analiz durmaz; eksik delil not olarak profile yazılır.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from api.config import settings
from api.schemas.dossier import ProductDossier

logger = logging.getLogger("EvidencePool")

URL_TIMEOUT_S = 5
URL_MAX_BYTES = 2 * 1024 * 1024
URL_MAX_REDIRECTS = 3
URL_TEXT_CHARS = 6000

_MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


@dataclass
class EvidencePool:
    dossier: ProductDossier
    url_text: Optional[str] = None
    attachments: List[tuple] = field(default_factory=list)  # (gs_uri, mime)
    notes: List[str] = field(default_factory=list)


class UnsafeURLError(ValueError):
    pass


def _check_public_host(url: str) -> None:
    """Yalnız herkese açık adreslere izin verir (SSRF).

    Sunucu, iç ağdaki servislere veya metadata uç noktasına (169.254.169.254)
    kullanıcı adına istek atmamalı. Her yönlendirme adımı ayrıca denetlenir.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeURLError("Yalnız http/https bağlantılarına izin verilir.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Alan adı çözümlenemedi: {parsed.hostname}") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private or address.is_loopback or address.is_link_local
            or address.is_reserved or address.is_multicast or address.is_unspecified
        ):
            raise UnsafeURLError("İç ağ veya özel adreslere istek atılamaz.")


def html_to_text(html: str, limit: int = URL_TEXT_CHARS) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    body = " ".join(soup.get_text(" ", strip=True).split())
    text = f"{title}\n{body}" if title and title not in body[:200] else body
    return text[:limit]


def fetch_url_text(url: str) -> str:
    """Ürün sayfasının okunabilir metnini döndürür; güvensiz veya başarısızsa hata fırlatır."""
    import requests

    current = url
    for _ in range(URL_MAX_REDIRECTS + 1):
        _check_public_host(current)
        response = requests.get(
            current,
            timeout=URL_TIMEOUT_S,
            allow_redirects=False,
            stream=True,
            headers={"User-Agent": "Mozilla/5.0 (GTIP-Karar-Destek; urun-sayfasi-okuyucu)"},
        )
        if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("Yönlendirme adresi yok.")
            current = urljoin(current, location)
            continue
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if "html" not in content_type and "text" not in content_type:
            response.close()
            raise ValueError(f"Sayfa metin değil ({content_type or 'bilinmiyor'}).")
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > URL_MAX_BYTES:
                break
            chunks.append(chunk)
        response.close()
        raw = b"".join(chunks)
        encoding = response.encoding or "utf-8"
        return html_to_text(raw.decode(encoding, errors="replace"))
    raise ValueError("Çok fazla yönlendirme.")


def attachment_mime(uri: str) -> Optional[str]:
    return _MIME_BY_EXT.get(os.path.splitext(uri.lower())[1])


def collect(dossier: ProductDossier) -> EvidencePool:
    pool = EvidencePool(dossier=dossier)

    if dossier.product_url:
        if settings.USE_GCP_EMULATOR or settings.ENVIRONMENT == "testing":
            pool.notes.append("Ürün sayfası test ortamında çekilmedi.")
        else:
            try:
                pool.url_text = fetch_url_text(dossier.product_url)
                if not pool.url_text.strip():
                    pool.notes.append("Ürün sayfasında okunabilir metin bulunamadı.")
            except UnsafeURLError as exc:
                pool.notes.append(f"Ürün sayfası güvenlik nedeniyle çekilmedi: {exc}")
            except Exception as exc:
                logger.warning("Ürün sayfası çekilemedi (%s): %s", dossier.product_url, exc)
                pool.notes.append("Ürün sayfasına ulaşılamadı; profil diğer delillerle çıkarıldı.")

    for uri in dossier.attachment_uris:
        mime = attachment_mime(uri)
        if mime:
            pool.attachments.append((uri, mime))
        else:
            pool.notes.append(f"Desteklenmeyen ek atlandı: {os.path.basename(uri)}")
    return pool
