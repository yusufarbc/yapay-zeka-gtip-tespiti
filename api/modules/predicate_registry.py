"""
TGTC Yasal Koşul Ağacı (Legal Predicate Registry).
Türk Gümrük Tarife Cetveli (TGTC) 99 Fasıl İzahnameleri ve Genel Yorum Kuralları (GİR 1-6) 
uyarınca GTİP pozisyonları için zorunlu yasal şartları (Boolean Predicates) tanımlar.
"""

from typing import List, Dict, Any, Optional
from api.schemas.predicate import LegalPredicate

PREDICATE_REGISTRY: Dict[str, List[LegalPredicate]] = {
    # 8542.31: Monolitik Entegre Devreler / Güç Entegreleri
    "8542.31": [
        LegalPredicate(
            predicate_id="P_8542_1",
            description="Ürün bir monolitik/hibrit elektronik entegre devre mi veya yarı iletken çip mi?",
            required_value="TRUE",
            statute_reference="TGTC Pozisyon 8542 İzahnamesi & Not 9"
        ),
        LegalPredicate(
            predicate_id="P_8542_2",
            description="Ürün elektronik sistemlerde güç yönetimi, voltaj düzenlemesi veya mantıksal işlem yapıyor mu?",
            required_value="TRUE",
            statute_reference="TGTC Pozisyon 8542.31 Alt Pozisyon Notu"
        )
    ],
    # 8517.13: Akıllı Cep Telefonları
    "8517.13": [
        LegalPredicate(
            predicate_id="P_8517_1",
            description="Ürün hücresel ağlar (5G/LTE/GSM) üzerinden ses veya veri iletimi yapan akıllı cep telefonu mu?",
            required_value="TRUE",
            statute_reference="TGTC Pozisyon 8517.13 Alt Pozisyon Notu"
        )
    ],
    # 8509.80: Şarjlı / Elektrikli Ev Aletleri (Diş Fırçaları vb.)
    "8509.80": [
        LegalPredicate(
            predicate_id="P_8509_1",
            description="Ürün kendinden dahili elektrik motorlu ev aleti veya kişisel bakım cihazı mı?",
            required_value="TRUE",
            statute_reference="TGTC Pozisyon 8509 İzahnamesi & GİR 1"
        ),
        LegalPredicate(
            predicate_id="P_8509_2",
            description="Ürünün toplam ağırlığı 20 kg'ın altında mıdır?",
            required_value="TRUE",
            statute_reference="TGTC 85. Fasıl Not 4"
        )
    ],
    # 8504.40: Statik Konvertörler / Şarj Adaptörleri
    "8504.40": [
        LegalPredicate(
            predicate_id="P_8504_1",
            description="Ürün elektrik enerjisini dönüştüren güç dönüştürücü veya şarj adaptörü mü?",
            required_value="TRUE",
            statute_reference="TGTC Pozisyon 8504 İzahnamesi"
        )
    ],
    # 6403.99: Hakiki Deri Ayakkabılar
    "6403.99": [
        LegalPredicate(
            predicate_id="P_6403_1",
            description="Dış yüzeyi (yüz malzemesi) hakiki deriden mamul müdür?",
            required_value="TRUE",
            statute_reference="TGTC 64. Fasıl Not 3a"
        )
    ],
    # 4202.21: Hakiki Deri El Çantaları
    "4202.21": [
        LegalPredicate(
            predicate_id="P_4202_1",
            description="Ürün dış yüzeyi hakiki deriden mamul el çantası, omuz çantası veya cüzdan mıdır?",
            required_value="TRUE",
            statute_reference="TGTC Pozisyon 4202 İzahnamesi"
        )
    ],
    # 6109.10: Pamuklu Örme T-Shirt
    "6109.10": [
        LegalPredicate(
            predicate_id="P_6109_1",
            description="Eşya örme (knitted / crocheted) t-shirt veya fanila mıdır?",
            required_value="TRUE",
            statute_reference="TGTC Pozisyon 6109 İzahnamesi"
        ),
        LegalPredicate(
            predicate_id="P_6109_2",
            description="İçerdiği pamuk oranı ağırlık itibarıyla en az %50 veya daha fazla mıdır?",
            required_value="TRUE",
            statute_reference="TGTC 61. Fasıl Notları & GİR 3b"
        )
    ],
    # 3303.00: Parfümler
    "3303.00": [
        LegalPredicate(
            predicate_id="P_3303_1",
            description="Ürün koku verici sıvı parfüm veya tuvalet suyu mudur?",
            required_value="TRUE",
            statute_reference="TGTC Pozisyon 3303 İzahnamesi"
        )
    ],
    # 9403.60: Ahşap Mobilyalar
    "9403.60": [
        LegalPredicate(
            predicate_id="P_9403_1",
            description="Ürün ahşap malzemeden imal edilmiş mobilya mıdır?",
            required_value="TRUE",
            statute_reference="TGTC Pozisyon 9403 İzahnamesi"
        )
    ],
    # 9503.00: Oyuncaklar
    "9503.00": [
        LegalPredicate(
            predicate_id="P_9503_1",
            description="Eşya çocukların veya yetişkinlerin eğlence/oyun amacıyla kullandığı oyuncak mıdır?",
            required_value="TRUE",
            statute_reference="TGTC Pozisyon 9503 İzahnamesi"
        )
    ],
    # 8712.00: Bisikletler
    "8712.00": [
        LegalPredicate(
            predicate_id="P_8712_1",
            description="Eşya motoru bulunmayan iki tekerlekli bisiklet midir?",
            required_value="TRUE",
            statute_reference="TGTC Pozisyon 8712 İzahnamesi"
        )
    ],
    # 8471.30: Dizüstü / Taşınabilir Bilgisayarlar
    "8471.30": [
        LegalPredicate(
            predicate_id="P_8471_1",
            description="Ağırlığı 10 kg'ı geçmeyen taşınabilir otomatik bilgi işlem makinesi midir?",
            required_value="TRUE",
            statute_reference="TGTC 8471.30 Alt Pozisyon Notu"
        ),
        LegalPredicate(
            predicate_id="P_8471_2",
            description="En az bir merkezi işlem birimi, bir klavye ve bir ekran içeriyor mu?",
            required_value="TRUE",
            statute_reference="TGTC 84. Fasıl Not 5A"
        )
    ]
}

class PredicateRegistryEngine:
    def get_predicates_for_gtip(self, gtip_code: str) -> List[LegalPredicate]:
        """
        GTİP koduna ait yasal koşul ağacını döndürür.
        Önce 6 haneli HS koduna, sonra 4 haneli pozisyona, ardından Fasıl düzeyine bakar.
        """
        from api.db.tgtc_knowledge_base import TGTC_CHAPTERS

        hs6 = gtip_code[:7].replace(".", "") if len(gtip_code) >= 6 else gtip_code[:6]
        pos4 = gtip_code[:4]
        chap2 = gtip_code[:2]

        # 1. 6 haneli HS alt pozisyon kontrolü
        for k in PREDICATE_REGISTRY:
            clean_k = k.replace(".", "")
            if clean_k == hs6 or clean_k == gtip_code[:len(clean_k)]:
                return PREDICATE_REGISTRY[k]

        # 2. 4 haneli pozisyon kontrolü
        for k in PREDICATE_REGISTRY:
            clean_k = k.replace(".", "")
            if clean_k[:4] == pos4:
                return PREDICATE_REGISTRY[k]

        # 3. 99 Fasıl TGTC Mevzuat İzahnamesinden Dinamik Yasal Predikat Türetimi
        chap_title = TGTC_CHAPTERS.get(chap2, "Genel Gümrük Tarife Cetveli Eşyası")

        return [
            LegalPredicate(
                predicate_id=f"P_{chap2}_{pos4}",
                description=f"Ürün TGTC Fasıl {chap2} ({chap_title}) kapsamındaki {pos4} pozisyonu yasal tanımına ve teknik spesifikasyonlarına uygun mudur?",
                required_value="TRUE",
                statute_reference=f"TGTC Fasıl {chap2} İzahnamesi, Madde {pos4} & GİR 1/6"
            )
        ]

predicate_registry = PredicateRegistryEngine()
