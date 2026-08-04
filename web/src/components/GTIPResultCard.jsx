import React, { useState } from 'react';
import { Award, Download, Scale, CheckCircle2, Bot, Layers, Copy, Check } from 'lucide-react';
import { getPDFReportUrl } from '../api/client';

export const GTIPResultCard = ({ decision }) => {
  const [copied, setCopied] = useState(false);

  if (!decision || (!decision.gtip_code && decision.status !== 'COMPLETED' && decision.status !== 'WAITING_FOR_USER')) return null;

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

  const handleCopy = () => {
    if (decision.gtip_code) {
      navigator.clipboard.writeText(decision.gtip_code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const breakdownLevels = [
    { title: '1. Fasıl (2 Hane)', code: fasil, desc: 'Bölüm / Fasıl Numarası' },
    { title: '2. Tarife Pozisyonu (4 Hane)', code: pozisyon, desc: 'Dünya Gümrük Örgütü' },
    { title: '3. HS Alt Pozisyonu (6 Hane)', code: hs6, desc: 'Uluslararası HS Standardı' },
    { title: '4. AB Kombine Kod (8 Hane)', code: cn8, desc: 'AB Ortak Tarife Pozisyonu' },
    { title: '5. Milli Pozisyon (10 Hane)', code: milli10, desc: 'Türkiye Milli Alt Açılımı' },
    { title: '6. Tam GTİP (12 Hane)', code: full12, desc: 'Nihai Vergi & İstatistik' },
  ];

  const confidencePercent = Math.round((decision.confidence_score || 0) * 100);

  // Dinamik Güven Seviyesi ve Şüpheli Durum Yönetimi
  let statusBadge = <span className="badge badge-success" style={{ padding: '4px 12px', fontSize: '0.8rem' }}>✓ Karar Kesinleşti (Yüksek Güven)</span>;
  let borderColor = 'var(--status-emerald-border)';
  let scoreColor = 'var(--status-emerald)';
  let scoreBg = 'var(--status-emerald-bg)';
  let scoreLabel = 'Yüksek Güven (Auditor Verified)';

  if (confidencePercent < 80 && confidencePercent >= 60) {
    statusBadge = <span className="badge badge-warning" style={{ padding: '4px 12px', fontSize: '0.8rem' }}>⚠️ ŞÜPHELİ / ORTA GÜVEN (Müşavir İncelemesi Önerilir)</span>;
    borderColor = 'var(--status-amber-border)';
    scoreColor = 'var(--status-amber)';
    scoreBg = 'var(--status-amber-bg)';
    scoreLabel = 'Şüpheli / Orta Güven';
  } else if (confidencePercent < 60) {
    statusBadge = <span className="badge badge-warning" style={{ padding: '4px 12px', fontSize: '0.8rem', background: '#fef2f2', color: '#dc2626', borderColor: '#fca5a5' }}>❌ DÜŞÜK GÜVEN / UYUMSUZ (Teknik Koşul Sağlanmadı)</span>;
    borderColor = 'rgba(239, 68, 68, 0.4)';
    scoreColor = '#dc2626';
    scoreBg = '#fef2f2';
    scoreLabel = 'Düşük Güven / Riskli';
  }

  return (
    <div className="glass-panel" style={{
      padding: '28px',
      marginBottom: '24px',
      border: `1.5px solid ${borderColor}`,
      background: 'var(--bg-surface)',
      boxShadow: 'var(--shadow-lg)'
    }}>
      
      {/* Üst Karar Başlığı */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
            {statusBadge}
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontFamily: 'monospace' }}>
              Oturum ID: {decision.session_id.substring(0, 8)}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <h2 className="font-mono" style={{ fontSize: '2.4rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '1px' }}>
              {decision.gtip_code}
            </h2>
            
            <button
              onClick={handleCopy}
              className="btn-secondary"
              style={{ padding: '6px 12px', fontSize: '0.78rem', gap: '5px' }}
              title="GTİP Kodunu Kopyala"
            >
              {copied ? <Check size={14} color="var(--status-emerald)" /> : <Copy size={14} />}
              <span>{copied ? 'Kopyalandı!' : 'Kopyala'}</span>
            </button>

            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary"
              style={{
                padding: '6px 14px',
                fontSize: '0.78rem',
                gap: '6px',
                textDecoration: 'none',
                display: 'inline-flex',
                alignItems: 'center',
                background: 'var(--accent-blue)',
                color: '#ffffff',
                borderRadius: '8px',
                fontWeight: 600
              }}
              title="Gümrük Müşaviri Resmi PDF Karar Raporunu İndir"
            >
              <Download size={14} />
              <span>Resmi PDF Raporu</span>
            </a>
          </div>

          <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', marginTop: '6px' }}>
            12 Haneli Resmi Türk Gümrük Tarife İstatistik Pozisyonu (GTİP) Kodu
          </p>

          {/* Ticaret Politikası & Ön Denetim Uyarı Etiketleri */}
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '10px' }}>
            <span style={{ fontSize: '0.72rem', background: 'rgba(59, 130, 246, 0.1)', color: '#2563eb', padding: '3px 8px', borderRadius: '6px', border: '1px solid rgba(59, 130, 246, 0.2)', fontWeight: 600 }}>
              🛡️ Gözetim Belgesi Tabiiliği Kontrolü
            </span>
            <span style={{ fontSize: '0.72rem', background: 'rgba(245, 158, 11, 0.1)', color: '#d97706', padding: '3px 8px', borderRadius: '6px', border: '1px solid rgba(245, 158, 11, 0.2)', fontWeight: 600 }}>
              ⚖️ İGV (İlave Gümrük Vergisi) Tabiiliği
            </span>
            <span style={{ fontSize: '0.72rem', background: 'rgba(16, 185, 129, 0.1)', color: '#059669', padding: '3px 8px', borderRadius: '6px', border: '1px solid rgba(16, 185, 129, 0.2)', fontWeight: 600 }}>
              📋 TSE / CE Teknik Düzenleme Standardı
            </span>
          </div>
        </div>

        {/* Güven Skoru Göstergesi */}
        <div style={{
          textAlign: 'right',
          background: scoreBg,
          padding: '12px 20px',
          borderRadius: '12px',
          border: `1px solid ${borderColor}`,
          boxShadow: '0 2px 8px rgba(0, 0, 0, 0.05)'
        }}>
          <div className="font-mono" style={{ fontSize: '1.8rem', fontWeight: 800, color: scoreColor, lineHeight: 1 }}>
            %{confidencePercent}
          </div>
          <span style={{ fontSize: '0.76rem', color: scoreColor, fontWeight: 700, marginTop: '4px', display: 'block' }}>
            {scoreLabel}
          </span>
        </div>
      </div>

      {/* 6 Aşamalı Hiyerarşik GTİP Kod Açılımı Grid Kartı */}
      <div style={{
        background: 'var(--bg-primary)',
        padding: '20px',
        borderRadius: '12px',
        marginBottom: '24px',
        border: '1px solid var(--border-subtle)'
      }}>
        <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Layers size={18} color="var(--accent-blue)" />
          <span>6 Aşamalı Hiyerarşik GTİP Kodu Yapısal Açılımı:</span>
        </h4>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
          {breakdownLevels.map((lvl, index) => (
            <div key={index} style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              padding: '12px 14px',
              borderRadius: '10px',
              boxShadow: 'var(--shadow-sm)',
              transition: 'all 0.15s ease'
            }}>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block' }}>{lvl.title}</span>
              <span className="font-mono" style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-primary)', display: 'block', margin: '4px 0' }}>
                {lvl.code}
              </span>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', lineHeight: 1.3, display: 'block' }}>{lvl.desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* 1. Orijinal Resmi Mevzuat Maddesi */}
      <div style={{
        background: 'var(--bg-primary)',
        padding: '20px',
        borderRadius: '12px',
        marginBottom: '20px',
        border: '1px solid var(--border-subtle)'
      }}>
        <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Scale size={18} color="var(--text-secondary)" />
          <span>Resmi Mevzuat Maddesi (Veritabanı Orijinal Kaydı):</span>
        </h4>
        <p style={{ fontSize: '0.9rem', lineHeight: 1.6, color: 'var(--text-primary)', marginBottom: '14px', fontWeight: 500 }}>
          {statuteText}
        </p>

        {decision.applied_gir_rules && decision.applied_gir_rules.length > 0 && (
          <div>
            <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
              Uygulanan Genel Yorum Kuralları (GİR):
            </span>
            <ul style={{ listStyleType: 'disc', paddingLeft: '20px', fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              {decision.applied_gir_rules.map((rule, i) => (
                <li key={i}>{rule}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* 2. Yapay Zeka Ajan Değerlendirmesi */}
      {llmCommentary && (
        <div style={{
          background: 'var(--bg-surface-subtle)',
          padding: '20px',
          borderRadius: '12px',
          marginBottom: '24px',
          border: '1px solid var(--border-subtle)'
        }}>
          <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Bot size={18} color="var(--accent-blue)" />
            <span>Yapay Zeka Ajan Değerlendirmesi (LLM Commentary):</span>
          </h4>
          <p style={{ fontSize: '0.88rem', lineHeight: 1.6, color: 'var(--text-secondary)' }}>
            {llmCommentary}
          </p>
        </div>
      )}

      {/* Emsal BTB Kararları Tablosu */}
      {decision.precedent_btbs && decision.precedent_btbs.length > 0 && (
        <div style={{ marginBottom: '24px' }}>
          <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Award size={18} color="var(--status-amber)" />
            <span>Ticaret Bakanlığı Emsal BTB Kararları (%70 Ağırlık):</span>
          </h4>

          <div style={{ overflowX: 'auto', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.84rem', textAlign: 'left' }}>
              <thead>
                <tr style={{ background: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <th style={{ padding: '10px 14px', color: 'var(--text-secondary)', fontWeight: 700 }}>BTB No</th>
                  <th style={{ padding: '10px 14px', color: 'var(--text-secondary)', fontWeight: 700 }}>Tarih</th>
                  <th style={{ padding: '10px 14px', color: 'var(--text-secondary)', fontWeight: 700 }}>GTİP Kodu</th>
                  <th style={{ padding: '10px 14px', color: 'var(--text-secondary)', fontWeight: 700 }}>Emsal Ürün Açıklaması</th>
                </tr>
              </thead>
              <tbody>
                {decision.precedent_btbs.map((btb, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-surface)' }}>
                    <td style={{ padding: '10px 14px', fontWeight: 700, color: 'var(--text-primary)' }} className="font-mono">{btb.btb_no}</td>
                    <td style={{ padding: '10px 14px', color: 'var(--text-muted)' }}>{btb.issue_date}</td>
                    <td style={{ padding: '10px 14px', fontWeight: 700, color: 'var(--text-primary)' }} className="font-mono">{btb.gtip_code}</td>
                    <td style={{ padding: '10px 14px', color: 'var(--text-secondary)' }}>{btb.product_description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Alt Aksiyon Butonları */}
      <div style={{
        display: 'flex',
        justify: 'space-between',
        alignItems: 'center',
        borderTop: '1px solid var(--border-subtle)',
        paddingTop: '20px',
        flexWrap: 'wrap',
        gap: '14px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--status-emerald)', fontSize: '0.88rem', fontWeight: 700 }}>
          <CheckCircle2 size={18} />
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
          <span>Resmi GTİP & BTB Raporunu İndir (PDF)</span>
        </a>
      </div>

    </div>
  );
};
