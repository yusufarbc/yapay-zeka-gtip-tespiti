"""
Resmi Gazete Birebir (Exact-Match) Mevzuat Extraction Boru Hattı.

Süreç:
1. LLM İşaretleyici (Gemini Flash / Pydantic Structured Output): start_anchor ve end_anchor tespit eder.
2. Kopyalayıcı Katman (Deterministik Python String Slicer): raw_text[start_idx : end_idx] ile birebir kopyalama yapar.
3. Doğrulama ve Kayıt (Cloud SQL / PostgreSQL): GTİP hijyeni ve ON CONFLICT DO UPDATE upsert.
"""

import os
import sys
import re
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from api.config import settings
from api.db.database import SessionLocal, GumrukSiniflandirmaKarariModel, GumrukEmsalKararModel

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ExtractOfficialGazetteExact")


# ==============================================================================
# ADIM 1: Pydantic Şemaları (Multimodal ve LLM Çıktı Zırhı)
# ==============================================================================

class CustomsDecisionItem(BaseModel):
    karar_no: str = Field(default="", description="Tebliğ Sıra No veya Karar No")
    gtip_kodu: str = Field(description="12 haneli veya 8 haneli tam GTİP kodu (Örn: 4411.13.90.00.11)")
    esya_tanimi: str = Field(description="Eşyanın ebat, yoğunluk, hammadde, kullanım yeri vb. tablodaki tüm teknik detaylarını içeren eksiksiz tam tanımı")
    hukuki_gerekce: str = Field(description="Tablonun gerekçe sütunundaki GİR 1, GİR 6, Fasıl İzahnamesi vb. yasal sınıflandırma gerekçesi (Tebliğ giriş maddeleri hariç)")
    resmi_gazete_sayisi: str = Field(default="", description="Resmî Gazete Sayısı")
    yayin_tarihi: str = Field(default="", description="Resmî Gazete Yayın Tarihi YYYY-MM-DD")

class GazetteExtractionResult(BaseModel):
    items: List[CustomsDecisionItem] = Field(default_factory=list, description="Çıkarılan gümrük sınıflandırma kararları listesi")

class DecisionBoundary(BaseModel):
    gtip_code: str = Field(description="Metinde geçen 8, 10 veya 12 haneli GTİP kodu.")
    product_name: str = Field(default="", description="Sınıflandırılan ürünün/eşyanın kısa ve öz Türkçe adı (örn: 'kablosuz veri iletişim cihazı', 'çelik boru', 'şarap'). Metin yoksa boş bırak.")
    start_anchor: str = Field(description="Karar paragrafının BAŞINDAKİ ilk 5-8 kelime (birebir orijinal metindeki kelimeler).")
    end_anchor: str = Field(description="Karar paragrafının SONUNDAKİ son 5-8 kelime (birebir orijinal metindeki kelimeler).")

class BoundariesList(BaseModel):
    items: list[DecisionBoundary] = Field(description="Metinde tespit edilen tüm kararların konum sınırları.")


# ==============================================================================
# ADIM 1.5: Multimodal Tablo Ayrıştırıcı (Gemini 3.5 Flash Lite)
# ==============================================================================

def get_genai_client(project_id: str, location: str):
    """Vertex AI GenAI Client nesnesi oluşturur."""
    from google import genai
    return genai.Client(vertexai=True, project=project_id, location=location)

def extract_tables_from_gazette_pdf(pdf_bytes: bytes, pub_date: str, gazette_no: str) -> List[CustomsDecisionItem]:
    """
    Multimodal Gemini 3.5 Flash Lite kullanarak Resmî Gazete PDF tablolarındaki
    Gümrük Sınıflandırma Kararlarını (GTİP, detaylı teknik eşya tanımı ve GİR hukuki gerekçesini)
    görsel ve yapısal bütünlüğüyle ayıklar.
    """
    if not pdf_bytes or len(pdf_bytes) < 100:
        return []

    project_id = getattr(settings, "GCP_PROJECT_ID", os.getenv("GCP_PROJECT_ID", "gumruk-mevzuat"))
    location = getattr(settings, "GCP_REGION", os.getenv("GCP_REGION", "us-central1"))
    model_name = getattr(settings, "DEFAULT_LLM_MODEL", "gemini-2.5-flash")

    prompt = f"""
    Resmî Gazete Tarihi: {pub_date}, Sayı: {gazette_no}.
    Ekli PDF'teki Gümrük Tarife Cetveli Sınıflandırma Kararları tablosunu satır satır ayrıştır.
    
    KURALLAR:
    1. 'esya_tanimi': Tabloda yer alan ürünün tüm teknik özelliklerini (kalınlık, yoğunluk, kaplama, malzeme, ebat, kullanım amacı vb.) EKSİKSİZ aktar. Asla sadece genel ürün adı (örn: sadece 'laminat parke') yazma.
    2. 'hukuki_gerekce': Tablonun 4. sütunundaki GİR kurallarını (GİR 1, GİR 6, GİR 3b vb.) ve izahname gerekçesini harfi harfine al. Tebliğin 'MADDE 1' gibi idari giriş metinlerini ASLA gerekçe yapma.
    3. 'gtip_kodu': Standart noktalı formata normalize et (Örn: 4411.13.90.00.11 veya 8516.79.70.00.00).
    4. 'resmi_gazete_sayisi': '{gazette_no}'.
    5. 'yayin_tarihi': '{pub_date}'.
    """

    try:
        client = get_genai_client(project_id=project_id, location=location)
        
        # Prepare contents
        try:
            from google.genai import types
            contents = [
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                prompt
            ]
            config = types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=GazetteExtractionResult
            )
        except Exception:
            contents = [
                {"inline_data": {"mime_type": "application/pdf", "data": pdf_bytes}},
                prompt
            ]
            config = {
                "temperature": 0.0,
                "response_mime_type": "application/json",
                "response_schema": GazetteExtractionResult
            }

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config
        )
        if response and hasattr(response, "parsed") and response.parsed:
            items = response.parsed.items
            for it in items:
                if not it.yayin_tarihi:
                    it.yayin_tarihi = pub_date
                if not it.resmi_gazete_sayisi:
                    it.resmi_gazete_sayisi = gazette_no
            return items
        elif response and response.text:
            parsed = GazetteExtractionResult.model_validate_json(response.text)
            return parsed.items
        return []
    except Exception as e:
        logger.error(f"Multimodal PDF çıkarma hatası ({model_name}): {e}", exc_info=True)
        # Fallback to digital pdf extraction if genai fails or offline
        try:
            from scripts.parse_rg_pdf_digital import extract_gtip_records_from_digital_pdf
            digital_records = extract_gtip_records_from_digital_pdf(pdf_bytes)
            items = []
            for idx, dr in enumerate(digital_records, start=1):
                items.append(CustomsDecisionItem(
                    karar_no=str(idx),
                    gtip_kodu=dr.get("gtip_kodu", ""),
                    esya_tanimi=dr.get("esyain_tanimi", ""),
                    hukuki_gerekce=dr.get("hukuki_gerekce", ""),
                    resmi_gazete_sayisi=gazette_no,
                    yayin_tarihi=pub_date
                ))
            return items
        except Exception as fallback_e:
            logger.error(f"Fallback extraction da başarısız: {fallback_e}")
            return []


# ==============================================================================
# ADIM 2: LLM İşaretleyici (Boundary Finder) Fonksiyonu
# ==============================================================================

def find_decision_boundaries(raw_text: str) -> BoundariesList:
    """
    Google Vertex AI (IAM / Service Account ADC - Sıfır API Key) ve Pydantic Structured Output kullanarak
    metindeki kararların GTİP kodunu, product_name, start_anchor ve end_anchor kelime öbeklerini tespit eder.
    Yapay zeka mevzuat metni üretmez, sadece konum işaretler.
    """
    # 0. PRE-CHECK: Metin Damping, Gözetim, Kota veya İthalat Denetimi Tebliği ise Sınıflandırma Kararı değildir!
    _REDDEDILEN_TEBLIG_TIPLERI = [
        "haksız rekabetin önlenmesine ilişkin",
        "haksız rekabetin önlenmesi",
        "dampinge karşı önlem",
        "gözetim uygulanmasına ilişkin",
        "özel tüketim vergisi kanununa ekli",
        "özel iznine tabi maddelerin ithalat denetimi",
        "ithalat denetimi tebliğ",
        "ihracat kota miktarı",
    ]
    raw_lower = raw_text.lower()
    if any(p in raw_lower for p in _REDDEDILEN_TEBLIG_TIPLERI):
        logger.info("Metin Sınıflandırma Kararı değil (Damping/Gözetim/Kota/Mevzuat Tebliği). Atlanıyor.")
        return BoundariesList(items=[])

    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
    os.environ["GOOGLE_CLOUD_PROJECT"] = os.getenv("GCP_PROJECT_ID", "gumruk-mevzuat")
    os.environ["GOOGLE_CLOUD_LOCATION"] = os.getenv("VERTEX_AI_LOCATION", "us-central1")


    project_id = os.getenv("GCP_PROJECT_ID", "gumruk-mevzuat")
    location = os.getenv("VERTEX_AI_LOCATION", "us-central1")
    api_key = os.getenv("GEMINI_API_KEY", "")

    try:
        from google import genai
        from google.genai import types

        client = None
        client = genai.Client(vertexai=True, project=project_id, location=location)


        system_instruction = (
            "Sen Türk Resmi Gazete Metin İşaretleyicisi ve Detaylı Ürün Açıklaması Çıkarıcı Ajanısın.\n"
            "GÖREVİN: Resmi Gazete metnini okumak ve İÇERİSİNDEKİ GERÇEK GÜMRÜK SINIFLANDIRMA KARARLARI İÇİN:\n"
            "1. Metinde geçen 8, 10 veya 12 haneli GTİP kodunu ('gtip_code'),\n"
            "2. Sınıflandırılan eşyanın TAM VE DETAYLI TÜRKÇE ÜRÜN AÇIKLAMASINI ('product_name') — \n"
            "   Örnekler:\n"
            "   - 'Ateşleme sistemi elektrikli olanlardan yalnız plastik gövdeli doldurulabilen gazlı cep çakmakları'\n"
            "   - 'Emprenye edilmiş kağıtla kaplı, yoğunluğu 0.8 g/cm3 olan lif levhadan laminat yer döşemesi'\n"
            "   - 'Hücresel ağ üzerinden ses ve veri iletişimi sağlayan akıllı telefon'\n"
            "3. Karar paragrafının BAŞINDAKİ İLK 5 ila 8 KELİMEYİ ('start_anchor'),\n"
            "4. Karar paragrafının SONUNDAKİ SON 5 ila 8 KELİMEYİ ('end_anchor') tespit etmektir.\n\n"
            "ÇOK KATI ELEME VE REDDEDİLME KURALLARI:\n"
            "- İTHALAT DENETİM TEBLİĞLERİ, İTHALAT İZİN LİSTELERİ VEYA TEBLİĞ DEĞİŞİKLİK MADDELERİ SINIFLANDIRMA KARARI DEĞİLDİR.\n"
            "- 'Sağlık Bakanlığının Özel İznine Tabi Maddelerin İthalat Denetimi Tebliği', 'Aynı Tebliğin eki Ek-1'de yer alan tabloya satır eklenmiştir', '...satır yürürlükten kaldırılmıştır' GİBİ MEVZUAT METİNLERİNİ KESİNLİKLE ALMA.\n"
            "- Eğer metinde somut bir eşya/ürün sınıflandırılmıyorsa BOŞ LİSTE ('items: []') döndür.\n"
            "- 'start_anchor' ve 'end_anchor' SADECE VE SADECE METİNDEKİ ORİJİNAL KELİMELERDEN OLUŞMALIDIR."
        )


        user_prompt = f"RESMİ GAZETE METNİ:\n\"\"\"{raw_text}\"\"\""

        config = types.GenerateContentConfig(
            temperature=0.0,
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=BoundariesList,
        )

        candidate_models = [
            os.getenv("DEFAULT_LLM_MODEL", "gemini-2.5-flash-lite"),
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
        ]

        # Tekrarları temizle
        seen_m = set()
        candidate_models = [m for m in candidate_models if not (m in seen_m or seen_m.add(m))]


        response = None
        for m_name in candidate_models:
            try:
                logger.info(f"Vertex AI İstemcisi Çağrılıyor: Model={m_name}, Location={location}")
                response = client.models.generate_content(
                    model=m_name,
                    contents=user_prompt,
                    config=config,
                )
                if response:
                    break
            except Exception as e_mod:
                if "404" in str(e_mod) or "NOT_FOUND" in str(e_mod):
                    logger.warning(f"Model {m_name} Vertex AI'da bulunamadı (404), alternatif modele geçiliyor...")
                    continue
                else:
                    raise e_mod

        if response and hasattr(response, "parsed") and response.parsed:
            return response.parsed
        elif response and response.text:
            return BoundariesList.model_validate_json(response.text)
        else:
            logger.warning("LLM yanıtı boş döndü (Metinde karar bulunamadı).")
            return BoundariesList(items=[])


    except Exception as e:
        logger.error(f"LLM Boundary Finder hatası: {e}")
        return BoundariesList(items=[])



# ==============================================================================
# ADIM 3: Deterministik Python Kopyalama (String Slicing)
# ==============================================================================

def extract_exact_text_from_boundaries(raw_text: str, boundary: DecisionBoundary) -> Optional[str]:
    """
    LLM'den gelen start_anchor ve end_anchor değerlerini ham metin (raw_text) üzerinde arar.
    Bulunan karakter indeksleri aralığını (raw_text[start_idx : end_idx]) birebir kopyalar.
    Eğer anchor'lar eşleşmezse regex fallback mekanizması çalıştırarak GTİP'in etrafındaki orijinal paragrafı kopyalar.
    """
    start_anchor = boundary.start_anchor.strip()
    end_anchor = boundary.end_anchor.strip()
    gtip_code = boundary.gtip_code.strip()

    # 1. Doğrudan exact .find() araması
    start_idx = raw_text.find(start_anchor)
    end_idx = -1

    if start_idx != -1:
        end_idx = raw_text.find(end_anchor, start_idx)

    # 2. Esnek / Normalize Karakter Eşleşmesi (Boşluk/Satır Sonu Farklılıklarına Karşı)
    if start_idx == -1 or end_idx == -1:
        start_idx, end_idx = _find_normalized_indices(raw_text, start_anchor, end_anchor)

    # 3. Kopyalama işlemi
    if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
        sliced_text = raw_text[start_idx : end_idx + len(end_anchor)]
        # HARFİ HARFİNE DOĞRULAMA (Sanity Check)
        assert sliced_text in raw_text, "Kopyalanan metin ham metnin alt dizisi olmalıdır!"
        return sliced_text

    # 4. Fallback Mekanizması: Anchor eşleşmezse GTİP etrafındaki orijinal paragrafı kopyala
    logger.info(f"Anchor tam eşleşmedi ({start_anchor[:20]}... -> {end_anchor[-20:]}), regex fallback çalıştırılıyor.")
    return _extract_paragraph_by_gtip(raw_text, gtip_code)


def _find_normalized_indices(raw_text: str, start_anc: str, end_anc: str) -> tuple[int, int]:
    """
    Boşluk ve noktalama farklarına toleranslı olarak metindeki karakter indekslerini tespit eder.
    """
    def clean_pattern(txt: str) -> str:
        return re.escape(re.sub(r"\s+", " ", txt.strip()))

    start_pattern = clean_pattern(start_anc).replace(r"\ ", r"\s+")
    end_pattern = clean_pattern(end_anc).replace(r"\ ", r"\s+")

    start_match = re.search(start_pattern, raw_text, re.IGNORECASE)
    if not start_match:
        return -1, -1

    start_idx = start_match.start()

    end_match = re.search(end_pattern, raw_text[start_idx:], re.IGNORECASE)
    if not end_match:
        return -1, -1

    end_idx = start_idx + end_match.start()
    return start_idx, end_idx


def _extract_paragraph_by_gtip(raw_text: str, gtip_code: str) -> Optional[str]:
    """
    GTİP kodunun etrafındaki orijinal paragrafı raw_text üzerinden birebir kopyalar.
    """
    clean_code = re.sub(r"[^\d]", "", gtip_code)
    if not clean_code:
        return None

    pos = raw_text.find(gtip_code)
    if pos == -1:
        pos = raw_text.find(clean_code)

    if pos == -1:
        return None

    para_start = raw_text.rfind("\n\n", 0, pos)
    para_start = 0 if para_start == -1 else para_start + 2

    para_end = raw_text.find("\n\n", pos)
    para_end = len(raw_text) if para_end == -1 else para_end

    sliced = raw_text[para_start:para_end].strip()
    if sliced:
        assert sliced in raw_text
        return sliced
    return None


def _extract_product_name_from_text(text: str, gtip: str = "") -> str:
    """
    Resmi Gazete metninden gerçek ürün/eşya adını çıkarmak için
    çok katmanlı hiyerarşik regex stratejisi uygular.
    LLM'nin product_name'i boş döndürdüğü veya jenerik Tebliğ cümlesi verdiği durumlarda çalışır.
    """
    text = text.strip()

    _JENERIK_PATTERNS = [
        r"bu tebli[gğ]in amac[iı]", r"madde\s*\d+", r"ge[cç][iı]ci madde", r"soru[sş]turma konusu",
        r"ayn[iı] tebli[gğ]in eki", r"ek-[0-9]+", r"tarihli ve", r"m[uü]kerrer say[iı]l[iı]",
        r"karar[iı] eki karar[iı]n", r"[oö]zel t[uü]ketim vergisi", r"f[iı]kras[iı] uyar[iı]nca",
        r"y[uü]r[uü]rl[uü]kten kald[iı]r[iı]lm[iı][sş]t[iı]r", r"sat[iı]r eklenmi[sş]tir",
        r"tabloya", r"tablodaki", r"gt[iı]p numaral[iı]", r"g[uü]mr[uü]k tarife istatistik",
        r"yerli [uü]retici", r"soru[sş]turma", r"ithalatta haks[iı]z rekabet",
        r"haks[iı]z rekabetin [öo]nlenmesi", r"g[uü]mr[uü]k genel tebli[gğ]i",
        r"resm[iı] gazete", r"ama[cç] ve kapsam", r"kapsam[iı]nda yer alan",
    ]

    def _is_bad(s: str) -> bool:
        if not s or len(s.strip()) < 3:
            return True
        return any(re.search(p, s, re.IGNORECASE) for p in _JENERIK_PATTERNS)

    def _clean(s: str) -> str:
        s = re.sub(r"^[\*\s\-\d]{1,6}\s*", "", s.strip())
        s = re.sub(r"\[?\s*GT[İI]P\s*:?.*$", "", s, flags=re.IGNORECASE)
        return s.strip(" ,.-*")

    # 1. Tırnak içi gerçek ürün adı (Örn: "Etil Alkol", "Dezenfektan", "hidrojenortofosfat")
    quotes = re.findall(r'"([^"]{3,150})"', text)
    for q in quotes:
        q_clean = _clean(q)
        if q_clean and len(q_clean) >= 3 and not _is_bad(q_clean):
            return q_clean[:200]

    # 2. "Eşya Tanımı:" / "Konu:" etiketinden sonraki değeri al
    m = re.search(r"(?:e[sş]ya tan[iı]m[iı]|konu|[uü]r[uü]n)\s*:\s*(.+?)(?:\n|hukuki|gerek[cç]e|$)", text, re.IGNORECASE)
    if m:
        c = _clean(m.group(1))
        if c and len(c) > 4 and not _is_bad(c):
            return c[:200]

    # 3. "yer alan ... ithalatı/eşyası" kalıbı
    m = re.search(r"yer alan\s+(.+?)(?:\s+ithalat[iı]|\s+ihracat[iı]|\s+[uü]r[uü]n[uü]|\s+e[sş]yas[iı]|\s+iznine|\s+tabidir)", text, re.IGNORECASE)
    if m:
        c = _clean(m.group(1))
        if c and 4 < len(c) < 150 and not _is_bad(c):
            return c[:150]

    # Metinden rastgele tebliğ maddesi cümlesi döndürme!
    return ""



# ==============================================================================
# ADIM 4: Veri Hijyeni ve Veritabanı Kayıt (Cloud SQL / PostgreSQL)
# ==============================================================================

def clean_and_validate_gtip(gtip_raw: str) -> Optional[str]:
    """
    GTİP kodunu temizler. 6, 8, 10 veya 12 haneli sayısal değer içerdiğini ve
    2020-2026 tarih dizisi olmadığını, 01-97 arası geçerli bir TGTC pozisyonuna sahip olduğunu doğrular.
    """
    if not gtip_raw or re.search(r"[a-zA-Z]", str(gtip_raw)):
        return None
    cleaned = re.sub(r"[^\d]", "", str(gtip_raw).strip())
    if not cleaned.isdigit() or len(cleaned) not in [6, 8, 10, 12]:
        return None

    # Tarih dizisi kontrolü (20200101 - 20261231 gibi YYYYMMDD değerleri reddet)
    if re.match(r"^202[0-6](0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])", cleaned):
        return None

    # TGTC Fasıl aralığı doğrulama (01 - 97 arası geçerli fasıl kodu olmalıdır)
    chapter_num = int(cleaned[:2])
    if chapter_num < 1 or chapter_num > 97:
        return None

    return cleaned



def extract_and_save_official_gazette(
    raw_text: str,
    yayin_tarihi: str,
    resmi_gazete_sayisi: Optional[str] = None,
    kaynak_url: Optional[str] = None,
    db_session = None
) -> List[Dict[str, Any]]:
    """
    Resmi Gazete ham metninden birebir (exact-match) kararları süzer ve veritabanına UPSERT eder.
    """
    boundaries = find_decision_boundaries(raw_text)
    extracted_records = []
    processed_gtips = set()

    should_close_session = False
    if db_session is None:
        db_session = SessionLocal()
        should_close_session = True

    try:
        for b in boundaries.items:
            valid_gtip = clean_and_validate_gtip(b.gtip_code)
            if not valid_gtip:
                logger.warning(f"Geçersiz GTİP kodu atlandı: {b.gtip_code}")
                continue

            if valid_gtip in processed_gtips:
                continue

            exact_text = extract_exact_text_from_boundaries(raw_text, b)
            if not exact_text:
                logger.warning(f"GTİP {valid_gtip} için metin dilimlenemedi.")
                continue

            # Birebir doğrulama (Halüsinasyonsuzluk Garantisi)
            assert exact_text in raw_text, f"HATA: Kopyalanan metin ham metinde bulunamadı! ({valid_gtip})"

            processed_gtips.add(valid_gtip)

            # 1. Önce LLM'in çıkardığı product_name'i kullan
            esya_tanimi = str(b.product_name or "").strip()

            _jenerik_kaliplar = [
                "bu tebliğin amacı", "haksız rekabetin önlenmesi", "ithalatta haksız rekabet",
                "resmi gazete", "gümrük genel tebliği", "tebliğ no:", "tebliğ metni",
                "sınıflandırma kararı", "tarife cetveli", "amaç ve kapsam", "ithalat denetimi",
                "özel iznine tabi", "satır eklenmiştir", "yürürlükten kaldırılmıştır", "değiştirilmiştir",
                "eki ek-1'de yer alan", "tabloya", "tablodaki", "sağlık bakanlığının"
            ]

            if not esya_tanimi or any(k in esya_tanimi.lower() for k in _jenerik_kaliplar):
                esya_tanimi = _extract_product_name_from_text(exact_text, valid_gtip)

            # EĞER HALA GEÇERLİ ÜRÜN ADI BULUNAMADIYSA (Tebliğ değişikliği / Mevzuat maddesi ise):
            # KESİNLİKLE VERİTABANINA SAHTE PLACEHOLDER KAYDETME! SKİP ET.
            if not esya_tanimi or any(k in esya_tanimi.lower() for k in _jenerik_kaliplar):
                logger.warning(f"Geçersiz/Tebliğ listesi maddesi atlandı ({valid_gtip}): '{esya_tanimi}'")
                continue


            # 1. gumruk_siniflandirma_kararlari tablosuna UPSERT
            existing = db_session.query(GumrukSiniflandirmaKarariModel).filter(
                GumrukSiniflandirmaKarariModel.gtip_kodu == valid_gtip,
                GumrukSiniflandirmaKarariModel.yayin_tarihi == yayin_tarihi
            ).first()

            if existing:
                existing.hukuki_gerekce = exact_text
                existing.resmi_gazete_sayisi = resmi_gazete_sayisi or existing.resmi_gazete_sayisi
                existing.kaynak_url = kaynak_url or existing.kaynak_url
                existing.esya_tanimi = esya_tanimi
            else:
                new_karar = GumrukSiniflandirmaKarariModel(
                    karar_tipi="SINIFLANDIRMA_KARARI",
                    gtip_kodu=valid_gtip,
                    yayin_tarihi=yayin_tarihi,
                    resmi_gazete_sayisi=resmi_gazete_sayisi,
                    esya_tanimi=esya_tanimi,
                    hukuki_gerekce=exact_text,
                    kaynak_url=kaynak_url
                )
                db_session.add(new_karar)

            # 2. Geriye dönük RAG/Arama uyumluluğu için gumruk_emsal_kararlar tablosunu senkronize et
            referans_no = f"RG-{yayin_tarihi.replace('-', '')}-{valid_gtip}"
            existing_emsal = db_session.query(GumrukEmsalKararModel).filter(
                GumrukEmsalKararModel.referans_no == referans_no
            ).first()

            if not existing_emsal:
                emsal_rec = GumrukEmsalKararModel(
                    karar_tipi="SINIFLANDIRMA_KARARI",
                    referans_no=referans_no,
                    yayin_tarihi=yayin_tarihi,
                    resmi_gazete_sayisi=resmi_gazete_sayisi or "-",
                    gtip_kodu=valid_gtip,
                    esya_tanimi=esya_tanimi,
                    hukuki_gerekce=exact_text,
                    kaynak_url=kaynak_url
                )
                db_session.add(emsal_rec)

            extracted_records.append({
                "gtip_kodu": valid_gtip,
                "yayin_tarihi": yayin_tarihi,
                "resmi_gazete_sayisi": resmi_gazete_sayisi,
                "hukuki_gerekce": exact_text,
                "kaynak_url": kaynak_url
            })

        db_session.commit()
        logger.info(f"✅ Toplam {len(extracted_records)} adet birebir kararlar başarıyla veritabanına aktarıldı.")
        return extracted_records

    except Exception as e:
        db_session.rollback()
        logger.error(f"Veritabanı kayıt hatası: {e}")
        raise e
    finally:
        if should_close_session:
            db_session.close()


# ==============================================================================
# SCRIPT ÇALIŞTIRMA (CLI Test)
# ==============================================================================

if __name__ == "__main__":
    sample_gazette_text = """
T.C. TİCARET BAKANLIĞI
GÜMRÜKLER GENEL MÜDÜRLÜĞÜ
SINIFLANDIRMA KARARI

Resmi Gazete Tarihi: 15/10/2025  Sayı: 32900

Madde 1- Aşağıda özellikleri belirtilen eşya, Türk Gümrük Tarife Cetvelinin 8517.62.00.00.00 GTİP numarasında sınıflandırılmıştır.
Eşya Tanımı: Dahili Wi-Fi 6 modülüne sahip, 5 GHz bandında çalışan endüstriyel kablosuz veri aktarım cihazı.
Hukuki Gerekçe: Gümrük Genel Tebliği (Tarife-Sınıflandırma Kararları) uyarınca, eşyanın temel niteliği veri iletişim fonksiyonu olduğundan 8517.62.00.00.00 GTİP koduna tabidir.

Madde 2- Aşağıda özellikleri belirtilen eşya, Türk Gümrük Tarife Cetvelinin 8471.30.00.00.11 GTİP numarasında sınıflandırılmıştır.
Eşya Tanımı: Ağırlığı 1.2 kg olan, dokunmatik ekranlı ve bataryalı taşınabilir dijital bilgisayar.
Hukuki Gerekçe: GIR 1 ve GIR 6 yorum kuralları uyarınca 8471.30.00.00.11 pozisyonunda değerlendirilmiştir.
"""

    print("--- Official Gazette Exact Match Extractor Test ---")
    results = extract_and_save_official_gazette(
        raw_text=sample_gazette_text,
        yayin_tarihi="2025-10-15",
        resmi_gazete_sayisi="32900",
        kaynak_url="https://www.resmigazete.gov.tr/eskiler/2025/10/20251015-1.htm"
    )

    for r in results:
        print(f"\n[GTİP]: {r['gtip_kodu']}")
        print(f"[METİN BİREBİR KOPYA]:\n{r['hukuki_gerekce']}")
        print(f"[Orijinal Metinde Var Mı?]: {r['hukuki_gerekce'] in sample_gazette_text}")
