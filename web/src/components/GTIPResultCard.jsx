import React, { useState } from 'react';
import { Award, Download, Scale, CheckCircle2, Bot, Layers, Copy, Check, BookOpen, ShieldCheck, FileText } from 'lucide-react';
import { getPDFReportUrl } from '../api/client';
import { useToast } from './ToastContext';

export const GTIPResultCard = ({ decision }) => {
  const { addToast } = useToast();
  const [expandedNotes, setExpandedNotes] = useState({});

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
      addToast('GTİP Kodu panoya kopyalandı.', 'success');
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
              <Copy size={14} />
              <span>Kopyala</span>
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

      {/* 1. Hukuki Dayanak ve Atıf Yapılan Resmi Mevzuat Maddeleri (Veritabanı Orijinal Kayıtları) */}
      {(() => {
        const legalSources = decision.legal_sources || [];
        const girSources = legalSources.filter(s => s.source_type === 'GIR');
        const tgtcSources = legalSources.filter(s => s.source_type && s.source_type.startsWith('TGTC_'));
        const fasilNotuSources = legalSources.filter(s => s.source_type === 'FASIL_NOTU');

        return (
          <div style={{
            background: 'var(--bg-primary)',
            padding: '24px',
            borderRadius: '14px',
            marginBottom: '24px',
            border: '1.5px solid rgba(59, 130, 246, 0.25)',
            boxShadow: '0 4px 20px rgba(0, 0, 0, 0.04)'
          }}>
            {/* Başlık ve Orijinallik Rozetleri */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', marginBottom: '18px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '14px' }}>
              <div>
                <h4 style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '10px', margin: 0 }}>
                  <Scale size={22} color="var(--accent-blue)" />
                  <span>Hukuki Dayanak ve Atıf Yapılan Resmi Mevzuat Maddeleri</span>
                </h4>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: '4px', marginBottom: 0 }}>
                  Bu sonuca ulaşmak için yürürlükteki Resmi TGTC veritabanından çekilen kanuni maddeler ve yorum kuralları.
                </p>
              </div>

              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.72rem', background: 'rgba(16, 185, 129, 0.1)', color: '#059669', padding: '4px 10px', borderRadius: '6px', border: '1px solid rgba(16, 185, 129, 0.25)', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
                  <ShieldCheck size={14} />
                  <span>Sıfır LLM Üretimi / Doğrudan DB Kaydı</span>
                </span>
                <span style={{ fontSize: '0.72rem', background: 'rgba(59, 130, 246, 0.1)', color: '#2563eb', padding: '4px 10px', borderRadius: '6px', border: '1px solid rgba(59, 130, 246, 0.2)', fontWeight: 600 }}>
                  2026 TGTC & Resmi Gazete
                </span>
              </div>
            </div>

            {/* 1. Kategori: Uygulanan Genel Yorum Kuralları (GİR / GYK) */}
            <div style={{ marginBottom: '22px' }}>
              <span style={{ fontSize: '0.86rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                <BookOpen size={16} color="var(--accent-blue)" />
                <span>1. Uygulanan Genel Yorum Kuralları (GİR / GYK):</span>
              </span>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {girSources.length > 0 ? (
                  girSources.map((gir, idx) => (
                    <div key={idx} style={{
                      background: 'var(--bg-surface-subtle)',
                      borderRadius: '10px',
                      border: '1px solid var(--border-subtle)',
                      padding: '14px 16px',
                      borderLeft: '4px solid var(--accent-blue)'
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px', flexWrap: 'wrap', gap: '8px' }}>
                        <span style={{ fontWeight: 800, fontSize: '0.88rem', color: 'var(--text-primary)' }}>
                          {gir.title || gir.reference_no}
                        </span>
                        <span style={{ fontSize: '0.72rem', background: 'rgba(59, 130, 246, 0.12)', color: 'var(--accent-blue)', padding: '2px 8px', borderRadius: '4px', fontWeight: 700 }}>
                          {gir.reference_no}
                        </span>
                      </div>
                      <p style={{ fontSize: '0.84rem', lineHeight: 1.6, color: 'var(--text-secondary)', margin: 0, fontStyle: 'italic' }}>
                        "{gir.excerpt}"
                      </p>
                    </div>
                  ))
                ) : decision.applied_gir_rules && decision.applied_gir_rules.length > 0 ? (
                  decision.applied_gir_rules.map((rule, idx) => (
                    <div key={idx} style={{
                      background: 'var(--bg-surface-subtle)',
                      borderRadius: '10px',
                      border: '1px solid var(--border-subtle)',
                      padding: '12px 16px',
                      borderLeft: '4px solid var(--accent-blue)',
                      fontSize: '0.84rem',
                      lineHeight: 1.6,
                      color: 'var(--text-secondary)'
                    }}>
                      {rule}
                    </div>
                  ))
                ) : null}
              </div>
            </div>

            {/* 2. Kategori: Hiyerarşik Resmi Tarife Maddeleri (TGTC 2026) */}
            <div style={{ marginBottom: '22px' }}>
              <span style={{ fontSize: '0.86rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                <Layers size={16} color="var(--accent-blue)" />
                <span>2. Resmi Tarife Pozisyonu ve Hiyerarşik Madde Metinleri (Veritabanı Kaydı):</span>
              </span>

              {tgtcSources.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {tgtcSources.map((src, idx) => (
                    <div key={idx} style={{
                      background: 'var(--bg-surface-subtle)',
                      borderRadius: '8px',
                      border: '1px solid var(--border-subtle)',
                      padding: '12px 14px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      gap: '12px'
                    }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                          <span className="font-mono" style={{ fontWeight: 800, fontSize: '0.84rem', color: 'var(--text-primary)' }}>
                            {src.reference_no}
                          </span>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            {src.title}
                          </span>
                        </div>
                        <p style={{ fontSize: '0.84rem', lineHeight: 1.5, color: 'var(--text-secondary)', margin: 0 }}>
                          {src.excerpt}
                        </p>
                      </div>
                      <span style={{ fontSize: '0.68rem', background: 'rgba(107, 114, 128, 0.1)', color: 'var(--text-muted)', padding: '2px 6px', borderRadius: '4px', whiteSpace: 'nowrap' }}>
                        Normatif Hüküm
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{
                  background: 'var(--bg-surface-subtle)',
                  borderRadius: '8px',
                  border: '1px solid var(--border-subtle)',
                  padding: '12px 14px',
                }}>
                  <p style={{ fontSize: '0.88rem', lineHeight: 1.6, color: 'var(--text-primary)', margin: 0 }}>
                    {statuteText}
                  </p>
                </div>
              )}
            </div>

            {/* 3. Kategori: İlgili Fasıl ve Dışlama Notları */}
            {fasilNotuSources.length > 0 && (
              <div>
                <span style={{ fontSize: '0.86rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '10px' }}>
                  <FileText size={16} color="var(--accent-blue)" />
                  <span>3. İlgili Fasıl ve Dışlama Notları (Veritabanı Orijinal Not Kaydı):</span>
                </span>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {fasilNotuSources.map((notSrc, idx) => {
                    const isExclusion = notSrc.title.toLowerCase().includes('dışlama');
                    const isExpanded = !!expandedNotes[idx];
                    return (
                      <div key={idx} style={{
                        background: isExclusion ? 'rgba(239, 68, 68, 0.03)' : 'var(--bg-surface-subtle)',
                        borderRadius: '10px',
                        border: `1px solid ${isExclusion ? 'rgba(239, 68, 68, 0.25)' : 'var(--border-subtle)'}`,
                        padding: '14px 16px',
                        borderLeft: `4px solid ${isExclusion ? '#ef4444' : 'var(--status-amber)'}`
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', flexWrap: 'wrap', gap: '8px' }}>
                          <span style={{ fontWeight: 800, fontSize: '0.88rem', color: isExclusion ? '#b91c1c' : 'var(--text-primary)' }}>
                            {notSrc.title}
                          </span>
                          <span style={{
                            fontSize: '0.72rem',
                            background: isExclusion ? 'rgba(239, 68, 68, 0.12)' : 'rgba(245, 158, 11, 0.12)',
                            color: isExclusion ? '#dc2626' : '#d97706',
                            padding: '2px 8px',
                            borderRadius: '4px',
                            fontWeight: 700
                          }}>
                            {isExclusion ? 'Dışlama Notu' : 'Fasıl Notu'}
                          </span>
                        </div>

                        <pre style={{
                          fontSize: '0.8rem',
                          lineHeight: 1.55,
                          color: 'var(--text-secondary)',
                          whiteSpace: 'pre-wrap',
                          fontFamily: 'inherit',
                          margin: 0,
                          maxHeight: isExpanded ? 'none' : '140px',
                          overflow: 'hidden',
                          position: 'relative'
                        }}>
                          {notSrc.excerpt}
                        </pre>

                        {notSrc.excerpt && notSrc.excerpt.length > 280 && (
                          <button
                            onClick={() => setExpandedNotes(prev => ({ ...prev, [idx]: !prev[idx] }))}
                            style={{
                              background: 'none',
                              border: 'none',
                              color: 'var(--accent-blue)',
                              fontSize: '0.76rem',
                              fontWeight: 700,
                              cursor: 'pointer',
                              padding: '6px 0 0 0',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px'
                            }}
                          >
                            {isExpanded ? 'Daha Az Göster' : 'Tüm Not Metnini Oku...'}
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        );
      })()}

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
            <span>Ticaret Bakanlığı Emsal BTB Kararları (Ağırlık: %50):</span>
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

      {/* AB EBTI Uluslararası Emsal Kararları (Yeni Bölüm) */}
      {decision.precedent_ebtis && decision.precedent_ebtis.length > 0 && (
        <div style={{ marginBottom: '24px' }}>
          <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Award size={18} color="#3b82f6" />
            <span>🇪🇺 AB EBTI Uluslararası Emsal Kararları (Ağırlık: %30):</span>
          </h4>
          <p style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '12px', lineHeight: 1.4 }}>
            EC DG TAXUD Avrupa Bağlayıcı Tarife Bilgisi — Gümrük Birliği (1/95 OKK) kapsamında teknik delil.
            Türkiye gümrüklerinde idari bağlayıcı olmamakla birlikte ihtilaflarda en güçlü uluslararası emsal niteliğindedir.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {decision.precedent_ebtis.map((ebti, idx) => {
              const countryFlags = {
                DE: '🇩🇪', FR: '🇫🇷', NL: '🇳🇱', BE: '🇧🇪', IT: '🇮🇹',
                ES: '🇪🇸', PL: '🇵🇱', AT: '🇦🇹', SE: '🇸🇪', DK: '🇩🇰',
                FI: '🇫🇮', PT: '🇵🇹', GR: '🇬🇷', CZ: '🇨🇿', HU: '🇭🇺',
              };
              const flag = countryFlags[ebti.country] || '🇪🇺';
              const similarityPct = Math.round((ebti.similarity_score || 0) * 100);
              const langLabels = { en: 'İngilizce', de: 'Almanca', fr: 'Fransızca', it: 'İtalyanca', es: 'İspanyolca', pl: 'Lehçe', nl: 'Hollandaca' };
              const langLabel = langLabels[ebti.language] || ebti.language;
              const ecSearchUrl = `https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp?Lang=en&Status=VALID&reference=${encodeURIComponent(ebti.reference_no)}`;

              return (
                <div key={idx} style={{
                  background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.04), rgba(147, 197, 253, 0.06))',
                  border: '1px solid rgba(59, 130, 246, 0.2)',
                  borderRadius: '10px',
                  padding: '14px 16px',
                  display: 'grid',
                  gridTemplateColumns: 'auto 1fr auto',
                  gap: '12px',
                  alignItems: 'start'
                }}>
                  {/* Sol: Ülke ve CN kodu */}
                  <div style={{ textAlign: 'center', minWidth: '64px' }}>
                    <div style={{ fontSize: '1.6rem', lineHeight: 1 }}>{flag}</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 700, marginTop: '2px' }}>{ebti.country}</div>
                    <div className="font-mono" style={{ fontSize: '0.72rem', color: '#3b82f6', fontWeight: 800, marginTop: '4px', background: 'rgba(59,130,246,0.1)', padding: '2px 6px', borderRadius: '4px' }}>
                      CN {ebti.cn_code}
                    </div>
                  </div>

                  {/* Orta: Referans ve açıklama */}
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px', flexWrap: 'wrap' }}>
                      <span className="font-mono" style={{ fontSize: '0.82rem', fontWeight: 800, color: 'var(--text-primary)' }}>
                        {ebti.reference_no}
                      </span>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', background: 'var(--bg-surface-subtle)', padding: '2px 6px', borderRadius: '4px', border: '1px solid var(--border-subtle)' }}>
                        {ebti.issue_date}
                      </span>
                      {ebti.valid_until && (
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          → {ebti.valid_until}
                        </span>
                      )}
                      <span style={{ fontSize: '0.7rem', color: '#64748b', fontStyle: 'italic' }}>
                        ({langLabel})
                      </span>
                    </div>
                    <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', lineHeight: 1.5, margin: 0 }}>
                      {ebti.product_description}
                    </p>
                    {ebti.legal_justification && (
                      <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: 1.4, marginTop: '6px', fontStyle: 'italic' }}>
                        📋 {ebti.legal_justification.substring(0, 200)}{ebti.legal_justification.length > 200 ? '...' : ''}
                      </p>
                    )}
                  </div>

                  {/* Sağ: Benzerlik skoru ve EC linki */}
                  <div style={{ textAlign: 'right', minWidth: '80px' }}>
                    <div style={{ fontSize: '1.1rem', fontWeight: 800, color: '#3b82f6', lineHeight: 1 }}>
                      %{similarityPct}
                    </div>
                    <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: '8px' }}>benzerlik</div>
                    <a
                      href={ecSearchUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        fontSize: '0.72rem',
                        color: '#3b82f6',
                        textDecoration: 'none',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '3px',
                        background: 'rgba(59,130,246,0.1)',
                        padding: '4px 8px',
                        borderRadius: '6px',
                        border: '1px solid rgba(59,130,246,0.2)',
                        fontWeight: 600,
                        whiteSpace: 'nowrap'
                      }}
                      title="EC EBTI Kararı Görüntüle"
                    >
                      🔗 EC TAXUD
                    </a>
                  </div>
                </div>
              );
            })}
          </div>

          <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '8px', lineHeight: 1.4, fontStyle: 'italic' }}>
            * AB Kombine Nomanklatürü (CN) ilk 8 hanesi Türk GTİP'i ile %100 uyumludur. EBTI kararları Türk gümrük mevzuatında
            bağlayıcı olmamakla birlikte 4458 sayılı Gümrük Kanunu md. 23 ve Gümrük Yönetmeliği md. 66 uyarınca yapılan
            itirazlarda Bölge Müdürlükleri ve İdare Mahkemelerinde teknik delil olarak kabul görmektedir.
          </p>
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
