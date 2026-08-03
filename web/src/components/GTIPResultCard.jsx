import React from 'react';
import { Award, Download, Scale, CheckCircle2, Bot, Layers } from 'lucide-react';
import { getPDFReportUrl } from '../api/client';

export const GTIPResultCard = ({ decision }) => {
  if (!decision || decision.status === 'WAITING_FOR_USER') return null;

  const pdfUrl = getPDFReportUrl(decision.session_id);
  const statuteText = decision.official_statute_text || decision.legal_justification || "Resmi Gümrük Tarife Cetveli (TGTC) hükümleri uyarınca.";
  const llmCommentary = decision.llm_reasoning_commentary;

  // 12 Haneli GTİP Kodunu 6 Aşamalı Hiyerarşik Yapısına Ayrıştır
  const rawCode = (decision.gtip_code || "").replace(/\./g, "").padEnd(12, "0");
  const fasil = rawCode.substring(0, 2);
  const pozisyon = rawCode.substring(0, 4);
  const hs6 = rawCode.substring(0, 4) + "." + rawCode.substring(4, 6);
  const cn8 = rawCode.substring(0, 4) + "." + rawCode.substring(4, 6) + "." + rawCode.substring(6, 8);
  const milli10 = rawCode.substring(0, 4) + "." + rawCode.substring(4, 6) + "." + rawCode.substring(6, 8) + "." + rawCode.substring(8, 10);
  const full12 = decision.gtip_code;

  const breakdownLevels = [
    { title: '1. Fasıl (2 Hane)', code: fasil, desc: 'Bölüm / Fasıl Numarası' },
    { title: '2. Tarife Pozisyonu (4 Hane)', code: pozisyon, desc: 'Dünya Gümrük Örgütü Pozisyonu' },
    { title: '3. HS Alt Pozisyonu (6 Hane)', code: hs6, desc: 'Uluslararası HS Kod Standardı' },
    { title: '4. AB Kombine Kod (8 Hane)', code: cn8, desc: 'AB Ortak Tarife Pozisyonu' },
    { title: '5. Milli Pozisyon (10 Hane)', code: milli10, desc: 'Türkiye Milli Alt Açılımı' },
    { title: '6. Tam GTİP (12 Hane)', code: full12, desc: 'Nihai Vergi & İstatistik Kodu' },
  ];

  return (
    <div className="glass-panel" style={{
      padding: '24px',
      marginBottom: '24px',
      border: '1px solid var(--status-emerald-border)',
      background: 'var(--bg-surface)'
    }}>
      
      {/* Üst Karar Başlığı */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <span className="badge badge-success">✓ Karar Kesinleşti</span>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Oturum: {decision.session_id.substring(0, 8)}</span>
          </div>
          <h2 style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '1px', fontFamily: 'monospace' }}>
            {decision.gtip_code}
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
            12 Haneli Resmi Türk Gümrük Tarife İstatistik Pozisyonu (GTİP) Kodu
          </p>
        </div>

        {/* Güven Skoru Göstergesi */}
        <div style={{ textAlign: 'right', background: 'var(--status-emerald-bg)', padding: '10px 16px', borderRadius: '8px', border: '1px solid var(--status-emerald-border)' }}>
          <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--status-emerald)' }}>
            %{int_score(decision.confidence_score)}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--status-emerald)', fontWeight: 600 }}>Güven Skoru (Auditor Verified)</span>
        </div>
      </div>

      {/* 6 Aşamalı Hiyerarşik GTİP Kod Açılımı Grid Kartı */}
      <div style={{ background: 'var(--bg-primary)', padding: '16px', borderRadius: '8px', marginBottom: '20px', border: '1px solid var(--border-subtle)' }}>
        <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Layers size={16} color="var(--text-secondary)" />
          📊 6 Aşamalı Hiyerarşik GTİP Kodu Yapısal Açılımı:
        </h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '10px' }}>
          {breakdownLevels.map((lvl, index) => (
            <div key={index} style={{
              background: 'var(--bg-surface-subtle)',
              border: '1px solid var(--border-subtle)',
              padding: '10px 12px',
              borderRadius: '6px'
            }}>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block' }}>{lvl.title}</span>
              <span style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-primary)', fontFamily: 'monospace', display: 'block', margin: '2px 0' }}>
                {lvl.code}
              </span>
              <span style={{ fontSize: '0.70rem', color: 'var(--text-secondary)' }}>{lvl.desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 1. Orijinal Resmi Mevzuat Maddesi (Veritabanından Kural Tabanlı Çekim - SIFIR HALÜSİNASYON) */}
      <div style={{ background: 'var(--bg-primary)', padding: '16px', borderRadius: '8px', marginBottom: '16px', border: '1px solid var(--border-subtle)' }}>
        <h4 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Scale size={16} color="var(--text-secondary)" />
          📌 Resmi Mevzuat Maddesi (Veritabanı Kaydı):
        </h4>
        <p style={{ fontSize: '0.88rem', lineHeight: 1.5, color: 'var(--text-primary)', marginBottom: '12px', fontWeight: 500 }}>
          {statuteText}
        </p>

        {decision.applied_gir_rules && decision.applied_gir_rules.length > 0 && (
          <div>
            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Uygulanan Genel Yorum Kuralları (GİR):</span>
            <ul style={{ listStyleType: 'disc', paddingLeft: '18px', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              {decision.applied_gir_rules.map((rule, i) => (
                <li key={i}>{rule}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* 2. Yapay Zeka Ajan Değerlendirmesi ve Yorumu (LLM Commentary - Ayrı Bölüm) */}
      {llmCommentary && (
        <div style={{ background: 'var(--bg-surface-subtle)', padding: '16px', borderRadius: '8px', marginBottom: '20px', border: '1px solid var(--border-subtle)' }}>
          <h4 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Bot size={16} color="var(--text-secondary)" />
            💡 Yapay Zeka Ajan Değerlendirmesi (LLM Yorumu):
          </h4>
          <p style={{ fontSize: '0.86rem', lineHeight: 1.5, color: 'var(--text-secondary)' }}>
            {llmCommentary}
          </p>
        </div>
      )}

      {/* Emsal BTB Kararları Tablosu */}
      {decision.precedent_btbs && decision.precedent_btbs.length > 0 && (
        <div style={{ marginBottom: '20px' }}>
          <h4 style={{ fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Award size={16} color="var(--status-amber)" />
            Ticaret Bakanlığı Emsal BTB Kararları (%70 Ağırlık):
          </h4>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', textAlign: 'left' }}>
              <thead>
                <tr style={{ background: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <th style={{ padding: '8px 10px', color: 'var(--text-secondary)', fontWeight: 600 }}>BTB No</th>
                  <th style={{ padding: '8px 10px', color: 'var(--text-secondary)', fontWeight: 600 }}>Tarih</th>
                  <th style={{ padding: '8px 10px', color: 'var(--text-secondary)', fontWeight: 600 }}>GTİP Kodu</th>
                  <th style={{ padding: '8px 10px', color: 'var(--text-secondary)', fontWeight: 600 }}>Emsal Ürün Açıklaması</th>
                </tr>
              </thead>
              <tbody>
                {decision.precedent_btbs.map((btb, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '8px 10px', fontWeight: 700, color: 'var(--text-primary)' }}>{btb.btb_no}</td>
                    <td style={{ padding: '8px 10px', color: 'var(--text-muted)' }}>{btb.issue_date}</td>
                    <td style={{ padding: '8px 10px', fontWeight: 700, color: 'var(--text-primary)' }}>{btb.gtip_code}</td>
                    <td style={{ padding: '8px 10px', color: 'var(--text-secondary)' }}>{btb.product_description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Alt Aksiyon Butonları */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-subtle)', paddingTop: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--status-emerald)', fontSize: '0.85rem', fontWeight: 600 }}>
          <CheckCircle2 size={16} />
          <span>Gümrük Beyannamesine Aktarılmaya Hazır</span>
        </div>

        <a
          href={pdfUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary"
          style={{ textDecoration: 'none' }}
        >
          <Download size={16} />
          Resmi GTİP & BTB Raporunu İndir (PDF)
        </a>
      </div>

    </div>
  );
};

function int_score(score) {
  return Math.round((score || 0) * 100);
}
