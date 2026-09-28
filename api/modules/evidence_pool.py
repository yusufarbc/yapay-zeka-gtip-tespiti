"""Ürün dosyasındaki delilleri tek havuzda toplar.

Web'den veri çekilmez: genel web araması ölçümde ~25 sn sürüp çoğunlukla 504
ile boş dönüyordu; ürün sayfası linki alanı da gereksiz bulunup kaldırıldı.
Ekler (fotoğraf, katalog, teknik resim) modele doğrudan GCS URI'siyle verilir.

Delil toplanamazsa analiz durmaz; eksik delil not olarak profile yazılır.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from api.schemas.dossier import ProductDossier

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
    attachments: List[tuple] = field(default_factory=list)  # (gs_uri, mime)
    notes: List[str] = field(default_factory=list)


def attachment_mime(uri: str) -> Optional[str]:
    return _MIME_BY_EXT.get(os.path.splitext(uri.lower())[1])


def collect(dossier: ProductDossier) -> EvidencePool:
    pool = EvidencePool(dossier=dossier)
    for uri in dossier.attachment_uris:
        mime = attachment_mime(uri)
        if mime:
            pool.attachments.append((uri, mime))
        else:
            pool.notes.append(f"Desteklenmeyen ek atlandı: {os.path.basename(uri)}")
    return pool
