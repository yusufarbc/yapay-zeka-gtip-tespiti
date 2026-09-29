"""Ürün dosyası (kullanıcı girdisi) ve ürün profili (sınıflandırmaya giden bilgi).

Yalnız eşya adı doğru sınıflandırma için çoğu zaman yetersizdir: "cam balkon
sistemi" yazıldığında taşıyıcı malzeme hiç söylenmemiştir. Dosya, müşavirin
önerdiği alanları ayrı ayrı toplar; profil ise her bilginin NEREDEN geldiğini
taşır. Kullanıcının söylemediği ve delilde görünmeyen bilgi INFERRED'dir ve
kararı etkiliyorsa kullanıcıya teyit ettirilir.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

FactSource = Literal["USER", "DOCUMENT", "IMAGE", "INFERRED", "BROKER"]

SOURCE_LABELS_TR = {
    "USER": "kullanıcı beyanı",
    "DOCUMENT": "yüklenen doküman",
    "IMAGE": "ürün fotoğrafı",
    "INFERRED": "model varsayımı, teyit edilmedi",
    "BROKER": "müşavir teyidi",
}

MAX_ATTACHMENTS = 3


class ProductDossier(BaseModel):
    product_name: str = Field(min_length=2, max_length=300, description="Eşya adı")
    use_and_function: Optional[str] = Field(default=None, max_length=1000, description="Kullanım yeri ve işlevi")
    material: Optional[str] = Field(
        default=None, max_length=500,
        description="Makine/cihaz değilse mamul edildiği madde (plastik, çelik, kauçuk vb.)",
    )
    is_machine: bool = Field(default=False, description="Makine veya cihaz mı?")
    extra_description: Optional[str] = Field(default=None, max_length=5000, description="Ek açıklama")
    attachment_uris: List[str] = Field(
        default_factory=list, max_length=MAX_ATTACHMENTS,
        description="Fotoğraf, katalog, broşür, teknik resim (gs://…/uploads/)",
    )

    @field_validator("product_name", "use_and_function", "material", "extra_description", mode="before")
    @classmethod
    def strip_text(cls, value):
        if value is None:
            return None
        text = " ".join(str(value).split())
        return text or None

    def to_raw_text(self) -> str:
        """Denetim kaydı, emsal araması ve geriye uyumluluk için etiketli metin."""
        lines = [f"EŞYA ADI: {self.product_name}"]
        if self.use_and_function:
            lines.append(f"KULLANIM YERİ VE İŞLEVİ: {self.use_and_function}")
        if self.is_machine:
            lines.append("NİTELİK: Makine veya cihaz")
        elif self.material:
            lines.append(f"MALZEME: {self.material}")
        if self.extra_description:
            lines.append(f"EK AÇIKLAMA: {self.extra_description}")
        return "\n".join(lines)

    def has_evidence_attachments(self) -> bool:
        return bool(self.attachment_uris)


class ProfileFact(BaseModel):
    value: str = Field(max_length=500)
    source: FactSource
    evidence: Optional[str] = Field(default=None, max_length=500, description="Kaynaktan kısa alıntı veya gerekçe")

    def label(self) -> str:
        return f"{self.value} ({SOURCE_LABELS_TR.get(self.source, self.source)})"


class MaterialFact(ProfileFact):
    part: Optional[str] = Field(default=None, max_length=200, description="Hangi kısım (çerçeve, panel, gövde…)")
    main_part: bool = Field(
        default=True, description="Gövde/taşıyıcı/hacmin çoğu mu (aksesuar, conta, bağlantı elemanı değil)",
    )
    alternatives: List[str] = Field(
        default_factory=list, max_length=4,
        description="Malzeme varsayımsa, bu parça için yaygın diğer malzemeler (teyit sorusu seçenekleri)",
    )
    changes_classification: bool = Field(
        default=True,
        description="Parça alternatif malzemeden olsaydı tarife pozisyonu değişir miydi? Değişmezse teyit sorusu sorulmaz",
    )


class ProductProfile(BaseModel):
    """Sınıflandırmadan önce eşyanın ne olduğu, neyden yapıldığı ve ne işe yaradığı."""

    product_type: ProfileFact
    function: Optional[ProfileFact] = None
    use_place: Optional[ProfileFact] = None
    is_machine: bool = False
    materials: List[MaterialFact] = Field(default_factory=list, max_length=8)
    essential_material: Optional[MaterialFact] = Field(
        default=None, description="Özet için birincil malzeme (önce beyan/teyit); tarife hükmü değildir",
    )
    product_type_alternatives: List[str] = Field(default_factory=list, max_length=4)
    summary: Optional[str] = Field(default=None, max_length=800)
    evidence_notes: List[str] = Field(default_factory=list, description="Delil havuzundan gelen uyarılar")

    def as_prompt_text(self) -> str:
        """Sınıflandırma modeline kaynak etiketli profil metni.

        Yardımcı parçaların tahmin edilen malzemeleri ve özet cümlesi verilmez:
        özet cümlesi cam balkon için fasıl seçiminde modeli aynı cümleyi
        tekrarlayan bir döngüye soktu. Tahmin edilen işlev ve kullanım yeri
        KALIR: bunlar da çıkarılınca aynı 120 BTB numunesinde fasıl doğruluğu
        %62.5'ten %55.8'e düştü (ör. airsoft bilyesi 9306 yerine 3926).
        """
        lines = [f"EŞYA: {self.product_type.label()}"]
        if self.function:
            lines.append(f"İŞLEV: {self.function.label()}")
        if self.use_place:
            lines.append(f"KULLANIM YERİ: {self.use_place.label()}")
        lines.append("NİTELİK: makine veya cihaz" if self.is_machine else "NİTELİK: makine veya cihaz değil")
        # Esas niteliği hangi malzemenin verdiği bir tarife hükmüdür (GYK 3(b));
        # profil yalnız olguları (parça -> malzeme) verir, hükmü sınıflandırıcı kurar.
        for item in self.materials:
            if item.source == "INFERRED" and not (item.main_part and item.changes_classification):
                continue
            part = f"{item.part}: " if item.part else ""
            lines.append(f"MALZEME — {part}{item.label()}")
        return "\n".join(lines)
