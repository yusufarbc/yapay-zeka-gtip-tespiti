-- ==============================================================================
-- Türk Gümrük Tarife Cetveli (TGTC) & BTB Hiyerarşik Veri Tabanı Şeması
-- GCP AlloyDB / Cloud SQL (PostgreSQL + pgvector + ltree)
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "ltree";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 1. Merkezi Hiyerarşik Tarife Ağacı (ltree & Bi-temporal)
CREATE TABLE IF NOT EXISTS tariff_hierarchy (
    gtip_code VARCHAR(12) PRIMARY KEY,                         -- Örn: '851830000000'
    parent_gtip VARCHAR(12),                                   -- Örn: '85183000'
    path ltree NOT NULL,                                       -- Örn: '85.8518.851830.85183000.851830000000'
    level INT NOT NULL,                                        -- 2 (Fasıl), 4 (Poz), 6 (Alt Poz), 8 (CN8), 12 (İstatistik)
    description_tr TEXT NOT NULL,                              -- Resmi tarife pozisyon adı
    indent_level INT DEFAULT 0,                                -- Tire sayısı (Örn: 0: Başlık, 1: -, 2: --)
    is_leaf BOOLEAN DEFAULT FALSE,                             -- Beyan edilebilir nihai yaprak kod mu?
    valid_from DATE NOT NULL DEFAULT '2026-01-01',             -- Yürürlük başlangıcı (Valid Time)
    valid_to DATE DEFAULT NULL,                                -- Yürürlük bitişi (Geçerliyse NULL)
    system_created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, -- Kayıt zamanı (Transaction Time)
    metadata JSONB                                             -- Ek vergi ve mevzuat hükümleri
);

CREATE INDEX IF NOT EXISTS idx_tariff_path_gist ON tariff_hierarchy USING GIST (path);
CREATE INDEX IF NOT EXISTS idx_tariff_parent ON tariff_hierarchy(parent_gtip);
CREATE INDEX IF NOT EXISTS idx_tariff_level ON tariff_hierarchy(level);
CREATE INDEX IF NOT EXISTS idx_tariff_validity ON tariff_hierarchy(valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_tariff_is_leaf ON tariff_hierarchy(is_leaf);

-- 2. Bölüm ve Fasıl Açıklama / Dışlama Notları Kütüphanesi
CREATE TABLE IF NOT EXISTS chapter_section_notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    target_level VARCHAR(10) NOT NULL,                         -- 'SECTION' veya 'CHAPTER'
    target_code VARCHAR(10) NOT NULL,                          -- 'XVI' (Bölüm 16) veya '85' (Fasıl 85)
    note_type VARCHAR(20) NOT NULL,                            -- 'EXCLUSION' (Dışlama), 'INCLUSION', 'DEF'
    raw_content TEXT NOT NULL,                                 -- Orijinal kanuni not metni
    structured_rules JSONB,                                    -- Dışlanan eşya tanımları ve yönlendirme kuralları
    embedding vector(768),                                     -- text-embedding-005 vektör temsili
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notes_target ON chapter_section_notes(target_level, target_code);
CREATE INDEX IF NOT EXISTS idx_notes_type ON chapter_section_notes(note_type);

-- 3. Hukuki Normlar ve Emsal BTB Havuzu
CREATE TABLE IF NOT EXISTS legislation_and_btb (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_type VARCHAR(30) NOT NULL,                             -- 'BTB', 'SINIFLANDIRMA_KARARI', 'TEBLIG'
    reference_no VARCHAR(50),                                  -- BTB Sayısı veya Resmî Gazete No
    legal_rank INT NOT NULL DEFAULT 5,                         -- Norm Hiyerarşisi Puanı (1: Kanun - 5: BTB)
    gtip_code VARCHAR(12) REFERENCES tariff_hierarchy(gtip_code),
    commercial_name TEXT NOT NULL,                             -- Ticari eşya adı
    technical_specs TEXT,                                      -- Eşyanın teknik analizi ve gerekçesi
    embedding vector(768),                                     -- Hibrit arama embedding alanı
    valid_from DATE NOT NULL DEFAULT '2020-01-01',
    valid_to DATE DEFAULT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_leg_gtip ON legislation_and_btb(gtip_code);
CREATE INDEX IF NOT EXISTS idx_leg_doc_type ON legislation_and_btb(doc_type);
CREATE INDEX IF NOT EXISTS idx_leg_rank ON legislation_and_btb(legal_rank);
CREATE INDEX IF NOT EXISTS idx_leg_validity ON legislation_and_btb(valid_from, valid_to);

-- Hukuki kaynak envanteri. Otorite ve yürürlük, similarity skorundan önce gelir.
CREATE TABLE IF NOT EXISTS legal_source (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type VARCHAR(40) NOT NULL,                          -- TGTC, GIR, FASIL_NOTU, TEBLIG, BTB, IZAHNAME...
    authority_level SMALLINT NOT NULL CHECK (authority_level BETWEEN 1 AND 9),
    is_binding BOOLEAN NOT NULL DEFAULT FALSE,
    reference_no VARCHAR(150),
    title TEXT NOT NULL,
    source_url TEXT,
    source_document_id VARCHAR(150),
    tariff_year VARCHAR(10),
    effective_from DATE NOT NULL,
    effective_to DATE,
    supersedes_id UUID REFERENCES legal_source(id),
    content_hash VARCHAR(128) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_type, reference_no, effective_from, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_legal_source_effective
    ON legal_source(source_type, authority_level, effective_from, effective_to);

-- Hybrid retrieval metni; her chunk kendi hukuki kaynağına ve GTİP kapsamına bağlıdır.
CREATE TABLE IF NOT EXISTS document_chunk (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    legal_source_id UUID NOT NULL REFERENCES legal_source(id),
    gtip_code VARCHAR(12) REFERENCES tariff_hierarchy(gtip_code),
    chunk_type VARCHAR(40) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_document_chunk_gtip ON document_chunk(gtip_code);

-- Her karar tekrar üretilebilir bir audit kaydıdır; model cevabı tek başına hukuk dayanağı değildir.
CREATE TABLE IF NOT EXISTS classification_run (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(255) NOT NULL,
    query_text TEXT NOT NULL,
    extracted_facts JSONB NOT NULL,
    candidate_codes JSONB NOT NULL,
    selected_gtip VARCHAR(12),
    status VARCHAR(40) NOT NULL,
    confidence_score NUMERIC(5,4),
    tariff_year VARCHAR(10) NOT NULL,
    model_version VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS evidence_link (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    classification_run_id UUID NOT NULL REFERENCES classification_run(id),
    legal_source_id UUID NOT NULL REFERENCES legal_source(id),
    candidate_gtip VARCHAR(12),
    evidence_role VARCHAR(30) NOT NULL,                         -- NORMATIVE | INTERPRETIVE | PRECEDENT
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_evidence_link_run ON evidence_link(classification_run_id);

-- Geriye Dönük Uyumluluk Tabloları

CREATE TABLE IF NOT EXISTS tgtc_gtip_versions (
    id BIGSERIAL PRIMARY KEY,
    gtip_code VARCHAR(20) NOT NULL,
    level VARCHAR(10) NOT NULL,
    chapter_code VARCHAR(10),
    parent_code VARCHAR(20),
    description TEXT NOT NULL,
    tax_rate VARCHAR(50),
    unit VARCHAR(50),
    gecerlilik_baslangic DATE NOT NULL,
    gecerlilik_bitis DATE,
    kaynak_resmi_gazete_no VARCHAR(50),
    UNIQUE (gtip_code, gecerlilik_baslangic)
);

CREATE INDEX IF NOT EXISTS idx_gtip_version_validity
    ON tgtc_gtip_versions(gtip_code, gecerlilik_bitis);

-- Emsal BTB Kararları Tablosu
CREATE TABLE IF NOT EXISTS official_btb_decisions (
    btb_no VARCHAR(50) PRIMARY KEY,           -- Örn: 'TR-BTB-2025-085017'
    gtip_code VARCHAR(12) NOT NULL,
    chapter_code VARCHAR(2) NOT NULL,
    heading_code VARCHAR(4) NOT NULL,
    issue_date DATE NOT NULL,
    product_description TEXT NOT NULL,
    legal_justification TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_btb_chapter ON official_btb_decisions(chapter_code);
CREATE INDEX IF NOT EXISTS idx_btb_gtip ON official_btb_decisions(gtip_code);
