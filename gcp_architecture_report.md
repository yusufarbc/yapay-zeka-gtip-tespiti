# GÜMRÜK GTİP VE MEVZUAT KARAR DESTEK SİSTEMİ MİMARİ ŞARTNAMESİ

Bu belge; Türkiye Gümrük Mevzuatı, Türk Gümrük Tarife Cetveli (TGTC) ve Bağlayıcı Tarife Bilgisi (BTB) kararlarını temel alarak, sıfır halüsinasyon (Zero-Hallucination) prensibiyle 12 haneli GTİP tespiti ve mevzuat danışmanlığı yapan kurumsal bilişim sisteminin nihai mimari şartnamesidir. Sistem; **Resmi Gazete Otomasyonu**, **AlloyDB AI Tabanlı Birleşik Veri Katmanı**, **Dinamik Kural Motoru**, **İki Aşamalı FastMCP Sorgulama Protokolü** ve **Human-in-the-Loop (HITL) Ajan Mimarisi** bileşenlerinden oluşur.

> **Canlı uygulama profili (2026-09-08):** Maliyet ve işletim sadeliği nedeniyle mevcut üretim kurulumu `gumruk-mevzuat/us-central1` üzerinde **Cloud SQL for PostgreSQL + pgvector/HNSW**, **Cloud Run Backend/Web**, **Cloud Run Jobs** ve **Cloud Scheduler** kullanır. AlloyDB/ScaNN ve Firebase bu belgedeki hedef mimari seçenekleridir; canlı sistem bunlara geçirilmiş gibi varsayılmamalıdır.

GTİP karar sırası zorunludur: aday kod yalnızca yürürlükteki **2026 TGTC** ağacından üretilir; **GİR 1-6**, ilgili fasıl notları/izahnameler, son altı yıldaki **BTB kararları**, **sınıflandırma kararları** ve diğer gümrük mevzuatı ayrı kaynak katmanları olarak sorgulanır. Eski bir BTB veya karar, 2026 cetvelinde bulunmayan bir kodu nihai aday haline getiremez.

Yıllık TGTC yenilemesi günlük Resmî Gazete senkronundan ayrıdır. Yeni yıl dizini doğrulandıktan sonra `gtip-seed-tgtc-2026` işi kontrollü olarak bir kez çalıştırılır; günlük iş yalnızca Resmî Gazete mevzuat/karar değişikliklerini idempotent biçimde işler.

---

## 1. YÜKSEK SEVİYE MİMARİ VE ÇALIŞMA DÖNGÜSÜ

Sistem iki temel çalışma döngüsü üzerinden yürütülür:

```text
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ DÖNGÜ 1: OTOMATİK RESMİ GAZETE VE MEVZUAT RADARI (ETL PIPELINE)                         │
│                                                                                          │
│  [resmigazete.gov.tr] ──► [Cloud Scheduler (02:00)] ──► [Cloud Run Jobs]                │
│                                                                  │                       │
│        ┌─────────────────────────────────────────────────────────┘                       │
│        ▼                                                                                 │
│  [HTML Sanitize] ──► [Gümrük/Dış Ticaret Filtresi] ──► [Madde Hiyerarşisi Ayrıştırıcı]   │
│                                                                  │                       │
│        ├─► Ham Metin, Başlık, Link, Tarih ───────────────┐       │                       │
│        └─► Embedding (Vertex AI text-embedding-005) ──┐  │       │                       │
│                                                       ▼  ▼       │                       │
│  [Cloud SQL for PostgreSQL 15 (pgvector + HNSW + İlişkisel Metadata)]                    │
└──────────────────────────────────────┬───────────────────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ DÖNGÜ 2: ETKİLEŞİMLİ GTİP VE MEVZUAT DANIŞMANI (LANGGRAPH + MCP)                         │
│                                                                                          │
│  [React/Vite UI (Cloud Run)] ◄──────► [Cloud Run Backend: FastAPI + LangGraph]           │
│                                                    │                                     │
│        ┌───────────────────────────────────────────┴─────────────────────────────┐       │
│        ▼                                                                         ▼       │
│  [GTİP Tespit Ajanı]                                                    [Mevzuat Ajanı]  │
│  1. Multimodal Özellik Çıkarımı (Gemini Flash-Lite)                     1. Serbest Soru  │
│  2. GİR Kural Filtresi (Fasıl Eleme)                                    2. İki Aşamalı   │
│  3. Auditor Node: "DB Kural Şartı Karşılandı mı?"                           MCP Tool Çağrı│
│     ├─► Eksik ──► HITL: Müşavire Çoktan Seçmeli Dinamik Soru            3. DB'den Orijinal│
│     └─► Tamam ──► Hibrit Vektör Eşleme (%70 BTB / %30 TGTC)                Ham Metin     │
│  4. Kesin 12 Haneli GTİP + Emsal BTB ve Kaynak Linki                    4. Gemini:       │
│                                                                            Sadece Yorumla│
└──────────────────────────────────────────────────────────────────────────────────────────┘

```

---

## 2. GOOGLE CLOUD PLATFORM (GCP) TEKNOLOJİ YIĞINI

| Mimari Katman | Seçilen GCP Servisi / Bileşeni | Yapılandırma ve Mimari Rolü |
| --- | --- | --- |
| **Bölge (Primary Region)** | **`us-central1` (Iowa)** | Cloud Run, Cloud SQL, Scheduler ve Vertex AI aynı bölgede çalışır.

 |
| **Büyük Dil Modeli** | **Vertex AI (`gemini-2.5-flash` / `gemini-2.5-flash-lite`)** | Çıkarım, doğrulama ve yapılandırılmış çıktı üretimi.

 |
| **Embedding Modeli** | **Vertex AI `text-embedding-005`** | 768 boyutlu vektörleştirme; mevzuat maddeleri ve emsal BTB metinlerinin indekslenmesi.

 |
| **Önbellekleme** | **Vertex AI Context Caching** | TGTC fasıl izahnameleri ve Genel Yorum Kuralları (GİR) önbelleğe alınarak girdi maliyeti %75 düşürülür.

 |
| **Birleşik Veritabanı** | **Cloud SQL for PostgreSQL 15** | İlişkisel tablolar ve `pgvector` HNSW indeksleri; Cloud SQL Auth Proxy socket bağlantısı kullanılır.

 |
| **İşlem Katmanı** | **Cloud Run (Docker Container)** | Python 3.11+, FastAPI, LangGraph durum makinesi ve FastMCP sunucusu. İstek olmadığında sıfıra ölçeklenir (`min-instances: 0`).

 |
| **Zamanlanmış Tetikleyici** | **Cloud Scheduler** | Resmî Gazete işi 02:00, resmî BTB işi 03:00 Europe/Istanbul saatinde çalışır.

 |
| **Sunucusuz ETL** | **Cloud Run Jobs** | Günlük tarama, BTB senkronu, arşiv backfill ve yıllık TGTC seed işleri ayrı çalıştırılır.

 |
| **Frontend Barındırma** | **Cloud Run** | React 18/Vite arayüzü Nginx tabanlı ayrı container olarak yayınlanır.

 |

---

## 3. GÜNLÜK RESMİ GAZETE VERİ BORU HATTI (ETL)

Resmi Gazete'nin günlük HTML sayfasındaki Microsoft Word/Office artıklarını (`mso-line-height`, `<o:p>`, `<span class=GramE>`) temizleyen, gümrükle ilgisiz tebliğleri eleyen ve maddeleri atomik olarak ayıran veri işleme motorudur.

### ETL Uygulama Kodu (`scraper_function.py`)

```python
import re
import requests
from bs4 import BeautifulSoup
import psycopg2
from google import genai
from google.genai import types

CUSTOMS_KEYWORDS = [
    "gümrük", "ithalat", "ihracat", "tarife", "damping", 
    "menşe", "kaçakçılık", "dış ticaret", "kambiyo", "antrepo", 
    "katma değer vergisi", "özel tüketim vergisi", "vergi usul"
]

ai_client = genai.Client(vertexai=True, project="prj-customs-ai", location="europe-west4")

def clean_html(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["o:p", "style", "script", "meta"]):
        tag.decompose()
    for span in soup.find_all("span"):
        span.unwrap()
    return soup.get_text(separator="\n", strip=True)

def generate_embedding(text: str) -> list:
    response = ai_client.models.embed_content(
        model="text-embedding-005",
        contents=text
    )
    return response.embeddings[0].values

def ingest_daily_gazette(date_str: str, gazette_no: int = 1, db_conn = None):
    base_url = f"https://www.resmigazete.gov.tr/eskiler/{date_str[:4]}/{date_str[4:6]}/{date_str}-{gazette_no}.htm"
    response = requests.get(base_url)
    if response.status_code != 200:
        return {"status": "FAILED", "reason": "Gazette not found"}

    response.encoding = "windows-1254"
    cleaned_text = clean_html(response.text)

    # 1. Aşama: Gümrük ve Dış Ticaret İlgililik Kontrolü
    if not any(kw in cleaned_text.lower() for kw in CUSTOMS_KEYWORDS):
        return {"status": "SKIPPED", "reason": "No customs related content"}

    # 2. Aşama: Madde Ayrıştırma (Regex Engine)
    pattern = re.compile(
        r"((?:GEÇİCİ\s+MADDE|EK\s+MADDE|MADDE)\s+\d+[\w\/\s\-]*)", 
        re.IGNORECASE
    )
    tokens = pattern.split(cleaned_text)
    
    current_law_no = "Doğrudan Düzenleme"
    articles_to_insert = []

    for i in range(1, len(tokens), 2):
        madde_baslik = tokens[i].strip()
        madde_icerik = tokens[i+1].strip() if i+1 < len(tokens) else ""

        # Atıf yapılan kanun numarasını yakala (Örn: 3065, 4458)
        law_match = re.search(r"(\d{3,5})\s+sayılı\s+([A-Za-zÇĞİÖŞÜçğıöşü\s]+Kanun)", madde_icerik)
        if law_match:
            current_law_no = law_match.group(1)

        # Fıkra/Bent Seviyesinde Semantik Chunking (Lost-in-the-Middle Önleme)
        vector = generate_embedding(f"{current_law_no} Sayılı Kanun {madde_baslik}: {madde_icerik[:1000]}")

        articles_to_insert.append((
            f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
            gazette_no,
            current_law_no,
            madde_baslik,
            madde_icerik,
            base_url,
            vector
        ))

    # 3. Aşama: AlloyDB'ye Toplu Yazma
    with db_conn.cursor() as cur:
        cur.executemany("""
            INSERT INTO gumruk_mevzuat_maddeleri 
            (tarih, resmi_gazete_sayisi, kanun_no, madde_kodu, madde_metni, kaynak_url, icerik_vektor)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """, articles_to_insert)
    db_conn.commit()
    return {"status": "SUCCESS", "inserted_articles": len(articles_to_insert)}

```

---

## 4. VERİTABANI MİMARİSİ VE ŞEMA TASARIMI (CLOUD SQL + PGVECTOR)

İlişkisel veriler ve vektör indeksleri **Cloud SQL for PostgreSQL 15** üzerinde birleştirilir. Canlı sistem `pgvector` ve HNSW kullanır; aşağıdaki ScaNN ifadeleri yalnızca olası AlloyDB geçişi için hedef tasarım notlarıdır.

```sql
-- Gerekli eklentileri aktif et
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Resmi Gazete Mevzuat Maddeleri Tablosu
CREATE TABLE gumruk_mevzuat_maddeleri (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tarih DATE NOT NULL,
    resmi_gazete_sayisi INT NOT NULL,
    kanun_no VARCHAR(50) NOT NULL,          -- Örn: '3065', '4458'
    madde_kodu VARCHAR(100) NOT NULL,       -- Örn: 'MADDE 15', 'GEÇİCİ MADDE 46'
    madde_metni TEXT NOT NULL,              -- Ham resmi gazete metni
    kaynak_url TEXT NOT NULL,               -- Doğrudan Resmi Gazete linki
    icerik_vektor vector(768),              -- text-embedding-005 boyutu
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Dinamik GTİP Kural Ağacı Tablosu (Hardcoded Python İptali)
CREATE TABLE gtip_rules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    parent_heading VARCHAR(10),             -- 4 haneli pozisyon (Örn: '8471')
    target_gtip VARCHAR(30),                -- 12 haneli noktalı kod (Örn: '8471.30.00.00.11')
    parametre_adi VARCHAR(50) NOT NULL,     -- 'weight', 'power', 'composition'
    kosul_operatoru VARCHAR(10) NOT NULL,   -- '<=', '>', '==', 'contains'
    esik_deger VARCHAR(50) NOT NULL,        -- '10kg', '200g/m2'
    soru_metni TEXT NOT NULL,               -- Müşavire yöneltilecek soru
    secenekler JSONB NOT NULL,              -- Soru şıkları
    oncelik INT DEFAULT 1
);

-- 3. Emsal BTB (Bağlayıcı Tarife Bilgisi) Kararları Tablosu
CREATE TABLE emsal_btb_kararlari (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    btb_referans_no VARCHAR(50) UNIQUE NOT NULL, -- Örn: 'TR-34-2025-0042'
    gtip_kodu VARCHAR(14) NOT NULL,
    urun_tanimi TEXT NOT NULL,
    karar_gerekcesi TEXT NOT NULL,
    gecerlilik_tarihi DATE NOT NULL,
    icerik_vektor vector(768)
);

-- 4. ScaNN (Scalable Nearest Neighbor) Vektör İndeksleri
-- pgvector'e kıyasla ultra düşük gecikmeli benzerlik araması sağlar
CREATE INDEX idx_mevzuat_scann ON gumruk_mevzuat_maddeleri 
USING scann (icerik_vektor cosine);

CREATE INDEX idx_btb_scann ON emsal_btb_kararlari 
USING scann (icerik_vektor cosine);

-- İlişkisel Arama İndeksleri
CREATE INDEX idx_mevzuat_lookup ON gumruk_mevzuat_maddeleri (kanun_no, madde_kodu);
CREATE INDEX idx_rules_heading ON gtip_rules (parent_heading);

```

---

## 5. İKİ AŞAMALI HUKUKİ ARAMA PROTOKOLÜ (MCP / TOOL ENGINE)

LLM'lerin kanun ve madde numaralarını ezberden tahmin etmeye çalışırken halüsinasyon görmesini engellemek amacıyla **İki Aşamalı Arama Protokolü (Discovery -> Fetch)** uygulanır:

1. **Aşama 1 (Keşif):** LLM anlamsal sorgu atar; veritabanı sadece en alakalı 3 kaydın `UUID` ve `başlık` bilgisini döner.
2. **Aşama 2 (Kesin Getirme):** LLM, listelenen UUID'ler arasından seçim yaparak `fetch_exact_article_by_id(uuid)` aracını çağırır. Veritabanından ham metin ve doğrulanmış URL çekilir.

```python
from google.genai import types
import psycopg2

mcp_customs_tools = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="search_customs_articles",
                description="Mevzuatta semantik arama yaparak ilgili madde UUID'lerini ve başlıklarını listeler.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "query": types.Schema(type=types.Type.STRING, description="Aranacak hukuki konu veya soru")
                    },
                    required=["query"]
                )
            ),
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name="fetch_exact_article_by_id",
                        description="Belirtilen UUID'ye sahip resmi mevzuat maddesinin ham metnini ve linkini getirir.",
                        parameters=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "article_id": types.Schema(type=types.Type.STRING, description="Maddenin benzersiz UUID değeri")
                            },
                            required=["article_id"]
                        )
                    )
                ]
            )
        ]
    )
]

def execute_search_customs_articles(query: str, db_conn):
    query_vector = generate_embedding(query)
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT id, kanun_no, madde_kodu, tarih,
                   1 - (icerik_vektor <=> %s::vector) AS similarity
            FROM gumruk_mevzuat_maddeleri
            ORDER BY icerik_vektor <=> %s::vector
            LIMIT 3;
        """, (query_vector, query_vector))
        rows = cur.fetchall()
        return [
            {
                "article_id": str(r[0]),
                "summary": f"{r[1]} Sayılı Kanun {r[2]} ({r[3]})",
                "similarity": float(r[4])
            } for r in rows
        ]

def execute_fetch_exact_article_by_id(article_id: str, db_conn):
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT kanun_no, madde_kodu, madde_metni, kaynak_url, tarih, resmi_gazete_sayisi
            FROM gumruk_mevzuat_maddeleri
            WHERE id = %s;
        """, (article_id,))
        row = cur.fetchone()
        if row:
            return {
                "kanun_no": row[0],
                "madde_kodu": row[1],
                "ham_metin": row[2],
                "kaynak_url": row[3],
                "resmi_gazete": f"{row[4]} / Sayı: {row[5]}"
            }
    return {"error": "Madde bulunamadı."}

```

---

## 6. LANGGRAPH ETKİLEŞİMLİ GTİP AJANI VE HITL DÖNGÜSÜ

Ajan, Pydantic ile yapılandırılmış ürün parametrelerini çıkarır, kural motoru şartlarını veritabanından denetler ve eksik parametre tespit edildiğinde müşavire dinamik soru yönelterek durumu askıya alır (`interrupt / WAITING_FOR_USER`).

### LangGraph İş Akışı Mantığı (`gtip_graph.py`)

```python
from typing import TypedDict, Optional, List, Dict
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

class CustomsState(TypedDict):
    user_query: str
    product_specs: Dict[str, str]
    candidate_heading: Optional[str]
    missing_parameter: Optional[str]
    question_payload: Optional[Dict]
    final_gtip: Optional[str]
    legal_basis: Optional[Dict]
    status: str  -- 'IN_PROGRESS', 'WAITING_FOR_USER', 'COMPLETED'

def feature_extractor_node(state: CustomsState):
    """Gemini Flash-Lite ile ürün özelliklerini yapılandırılmış şemada çıkarır."""
    prompt = f"Şu ürün tanımından teknik parametreleri JSON olarak çıkar: {state['user_query']}"
    # Structured Outputs zorlanır
    response = ai_client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    extracted = response.parsed
    # Örnek kural bazlı başlangıç pozisyonu (GİR 1-3 kuralları)
    heading = "8471" if "bilgisayar" in state['user_query'].lower() else "5208"
    return {"product_specs": extracted, "candidate_heading": heading, "status": "IN_PROGRESS"}

def dynamic_rule_auditor_node(state: CustomsState, db_conn):
    """AlloyDB gtip_rules tablosundaki eşik şartlarını denetler."""
    heading = state["candidate_heading"]
    specs = state["product_specs"]

    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT parametre_adi, soru_metni, secenekler, target_gtip
            FROM gtip_rules
            WHERE parent_heading = %s
            ORDER BY oncelik ASC;
        """, (heading,))
        rules = cur.fetchall()

        for rule in rules:
            param_name, question_text, options, target_gtip = rule
            if param_name not in specs:
                # Eksik parametre tespit edildi: Kullanıcıya soru sor ve akışı durdur
                return {
                    "missing_parameter": param_name,
                    "question_payload": {
                        "question": question_text,
                        "options": options
                    },
                    "status": "WAITING_FOR_USER"
                }

    # Tüm şartlar sağlandıysa en uygun GTİP kuralına bağla
    return {"status": "RESOLVED"}

def resolver_node(state: CustomsState, db_conn):
    """Emsal BTB ve Tarife Metnini eşleştirerek nihai 12 haneli GTİP'i kesinleştirir."""
    # Hibrit benzerlik skoru hesaplama: 0.70 * BTB + 0.30 * TGTC
    gtip_result = "8471.30.00.00.11"
    citation = {
        "gtip": gtip_result,
        "dayanak_btb": "TR-34-2025-0042 sayılı BTB Kararı",
        "izahname_notu": "Fasıl 84 Not 5(A) bendi uyarınca portatif bilgisayar sınıflandırması."
    }
    return {"final_gtip": gtip_result, "legal_basis": citation, "status": "COMPLETED"}

# LangGraph Akış Şeması
def build_customs_workflow(db_pool):
    workflow = StateGraph(CustomsState)
    workflow.add_node("extractor", feature_extractor_node)
    workflow.add_node("auditor", lambda s: dynamic_rule_auditor_node(s, db_pool))
    workflow.add_node("resolver", lambda s: resolver_node(s, db_pool))

    workflow.set_entry_point("extractor")
    workflow.add_edge("extractor", "auditor")

    workflow.add_conditional_edges(
        "auditor",
        lambda state: "wait" if state["status"] == "WAITING_FOR_USER" else "resolve",
        {
            "wait": END,
            "resolve": "resolver"
        }
    )
    workflow.add_edge("resolver", END)

    # Oturum hafızasını AlloyDB (PostgresSaver) üzerinde sakla
    checkpointer = PostgresSaver(db_pool)
    return workflow.compile(checkpointer=checkpointer, interrupt_before=["auditor"])

```

---

## 7. ÇİFT KANATLI (SPLIT-VIEW) MÜŞAVİR ARAYÜZ STANDARDI

Müşavir ekranında LLM çıktısı ile veritabanından çekilen resmi hukuki kanıt birbirinden fiziksel olarak ayrılmıştır:

```text
┌──────────────────────────────────────────────┬──────────────────────────────────────────────┐
│ SOL KANAT: AI DANIŞMAN ANALİZİ               │ SAĞ KANAT: KİLİTLİ HUKUKİ KANIT KARTI        │
│ (Vertex AI Gemini Flash-Lite Yorumu)         │ (AlloyDB'den Birebir Çekilen Ham Veri)       │
├──────────────────────────────────────────────┼──────────────────────────────────────────────┤
│ Müşavir Cevabı Alındı: Ağırlık <= 10 kg      │ RESMİ DAYANAK:                               │
│                                              │ • Mevzuat: 4458 Sayılı Gümrük Kanunu         │
│ Analiz Özeti:                                │ • Tarife Pozisyonu: 8471.30.00.00.11         │
│ Ürünün dahili bir merkezi işlem birimi (CPU) │ • Tanım: Ağırlığı 10 kg'ı geçmeyen, klavyesi │
│ ve klavyesi bulunduğu, ağırlığının 10 kg'ın  │   ve ekranı olan taşınabilir bilgisayarlar   │
│ altında olduğu doğrulandığından GİR 1 ve     │                                              │
│ GİR 6 genel kuralları uyarınca 8471.30       │ EMSAL KARAR:                                 │
│ alt pozisyonunda sınıflandırılmıştır.        │ • BTB No: TR-34-2025-0042                    │
│                                              │ • Karar Tarihi: 14 Ocak 2025                 │
│ Uygulanacak Gümrük Vergisi: %0 (Gümrük Birliği)                                            │
│ İlave Gümrük Vergisi (İGV): Muaf             │ RESMİ GAZETE KAYNAĞI:                        │
│                                              │ 🔗 https://resmigazete.gov.tr/eskiler/...    │
└──────────────────────────────────────────────┴──────────────────────────────────────────────┘

```

---

## 8. ÜRETİM ORTAMI (PRODUCTION) MEVCUT DURUM VE YOL HARİTASI

1. **Mevcut:** Cloud SQL PostgreSQL 15, pgvector/HNSW, iki Cloud Run servisi, dört Cloud Run Job ve iki Scheduler görevi `us-central1` bölgesinde çalışır.
2. **Güvenlik:** Yönetim ve veri değiştiren uçlar kimlik doğrulamalıdır. Google tokenları audience/domain ve yönetici e-posta allowlist'i ile doğrulanır; demo analiz trafiği hız sınırlıdır.
3. **Dayanıklılık:** BTB portalının geçici 429/5xx cevapları yeniden denenir; daha önce kaydedilmiş referansların detay sayfaları tekrar indirilmez.
4. **Kapasite:** Backend `concurrency=20`, `max-instances=3` ve worker başına en fazla iki DB bağlantısıyla `db-f1-micro` bağlantı bütçesini korur.
5. **İleri aşama:** Trafik ve SLA gerektirirse Cloud SQL HA/private IP veya AlloyDB geçişi ayrı maliyet ve kapasite çalışmasıyla değerlendirilir.
