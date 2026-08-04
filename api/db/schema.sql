-- ==============================================================================
-- Türk Gümrük Tarife Cetveli (TGTC) & BTB Hiyerarşik Veri Tabanı Şeması
-- GCP Cloud SQL (PostgreSQL + pgvector)
-- ==============================================================================

CREATE TABLE IF NOT EXISTS tgtc_hierarchy (
    gtip_code VARCHAR(12) PRIMARY KEY,       -- Örn: '847130000011'
    chapter_code VARCHAR(2) NOT NULL,          -- Örn: '84'
    heading_code VARCHAR(4) NOT NULL,          -- Örn: '8471'
    subheading_code VARCHAR(6) NOT NULL,       -- Örn: '847130'
    cn8_code VARCHAR(8) NOT NULL,              -- Örn: '84713000'
    description_tr TEXT NOT NULL,
    valid_from DATE NOT NULL,
    valid_until DATE,                          -- NULL ise 2026 yılında aktiftir
    import_duty_rate NUMERIC(5,2) DEFAULT 0,  -- Gümrük Vergisi (%)
    additional_duty_rate NUMERIC(5,2) DEFAULT 0, -- İlave Gümrük Vergisi (%)
    vat_rate NUMERIC(5,2) DEFAULT 20.0,       -- KDV (%)
    metadata JSONB                             -- Ek İzahname Notları ve Tebliğler
);

CREATE INDEX IF NOT EXISTS idx_tgtc_chapter ON tgtc_hierarchy(chapter_code);
CREATE INDEX IF NOT EXISTS idx_tgtc_heading ON tgtc_hierarchy(heading_code);
CREATE INDEX IF NOT EXISTS idx_tgtc_valid ON tgtc_hierarchy(valid_until);

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
