import React from 'react';
import { Download, Copy, CheckCircle2, AlertTriangle, BookOpen, ChevronRight, Users, Package } from 'lucide-react';
import { getPDFReportUrl } from '../api/client';
import { useToast } from './ToastContext';

const LEVEL_LABELS = { CHAPTER: 'Fasıl', HEADING: 'Pozisyon', SUBHEADING: 'Alt pozisyon', GTIP: 'GTİP' };

// Model gerekçe yazmadıysa adımın nasıl seçildiği kullanıcıya söylenir.
const SOURCE_NOTES = {
  SINGLE_OPTION: 'Bu dalda tek resmî seçenek vardı.',
  RESIDUAL: "Model özel bir dal eşleştiremedi; resmî 'diğerleri' dalı seçildi.",
  BROKER: 'Müşavir seçti.',
};

const SOURCE_BADGES = {
  BROKER: { text: 'Müşavir seçimi', color: 'var(--accent-blue)' },
  RESIDUAL: { text: 'Kalıntı dalı', color: 'var(--status-amber)' },
  BTB_EXACT: { text: 'Birebir BTB', color: 'var(--status-emerald)' },
};

// Profildeki her bilginin kaynağı: kullanıcı neyi söyledi, sistem neyi varsaydı.
const FACT_SOURCES = {
  USER: { text: 'Beyan', color: 'var(--status-emerald)' },
  DOCUMENT: { text: 'Doküman', color: 'var(--accent-blue)' },
  IMAGE: { text: 'Fotoğraf', color: 'var(--accent-blue)' },
  INFERRED: { text: 'Varsayım', color: 'var(--status-amber)' },
  BROKER: { text: 'Müşavir teyidi', color: 'var(--status-emerald)' },
};

const SourceBadge = ({ source }) => {
  const meta = FACT_SOURCES[source] || { text: source, color: 'var(--text-muted)' };
  return (
    <span style={{ fontSize: '0.68rem', fontWeight: 700, color: meta.color, border: `1px solid ${meta.color}`, borderRadius: '6px', padding: '1px 6px', whiteSpace: 'nowrap' }}>
      {meta.text}
    </span>
  );
};

const ProductProfile = ({ profile }) => {
  if (!profile) return null;
  const rows = [
    ['Eşya', profile.product_type],
    ['İşlev', profile.function],
    ['Kullanım yeri', profile.use_place],
  ].filter(([, fact]) => fact?.value);
  return (
    <div style={{ marginBottom: '24px' }}>
      <h4 style={sectionTitle}><Package size={18} color="var(--accent-blue)" />Ürün profili</h4>
      <dl style={{ display: 'grid', gridTemplateColumns: 'max-content 1fr', gap: '6px 14px', margin: 0, fontSize: '0.86rem' }}>
        {rows.map(([label, fact]) => (
          <React.Fragment key={label}>
            <dt style={muted}>{label}</dt>
            <dd style={{ margin: 0, display: 'flex', gap: '8px', alignItems: 'baseline', flexWrap: 'wrap', color: 'var(--text-primary)' }}>
              {fact.value}<SourceBadge source={fact.source} />
            </dd>
          </React.Fragment>
        ))}
        <dt style={muted}>Nitelik</dt>
        <dd style={{ margin: 0, color: 'var(--text-primary)' }}>{profile.is_machine ? 'Makine veya cihaz' : 'Makine veya cihaz değil'}</dd>
        {!profile.is_machine && (profile.materials || []).map((m, idx) => (
          <React.Fragment key={`m${idx}`}>
            <dt style={muted}>{m.part ? `Malzeme (${m.part})` : 'Malzeme'}</dt>
            <dd style={{ margin: 0, display: 'flex', gap: '8px', alignItems: 'baseline', flexWrap: 'wrap', color: 'var(--text-primary)' }}>
              {m.value}<SourceBadge source={m.source} />
            </dd>
          </React.Fragment>
        ))}
      </dl>
      {(profile.evidence_notes || []).map((note, idx) => (
        <p key={idx} style={{ ...muted, margin: '8px 0 0' }}>{note}</p>
      ))}
    </div>
  );
};

const formatCode = (code) => {
  const d = String(code || '').replace(/\D/g, '');
  if (d.length === 12) return `${d.slice(0, 4)}.${d.slice(4, 6)}.${d.slice(6, 8)}.${d.slice(8, 10)}.${d.slice(10)}`;
  if (d.length === 6) return `${d.slice(0, 4)}.${d.slice(4)}`;
  return d;
};

const sectionTitle = { fontSize: '0.92rem', fontWeight: 700, color: 'var(--text-primary)', margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: '8px' };
const muted = { fontSize: '0.8rem', color: 'var(--text-muted)' };

export const GTIPResultCard = ({ decision }) => {
  const { addToast } = useToast();

  if (!decision || (!decision.gtip_code && decision.status !== 'COMPLETED')) return null;

  const needsReview = decision.legal_validation_status === 'MANUAL_REVIEW';
  const reviewNote = (decision.audit_notes || [])
    .find((note) => note.startsWith('BROKER_APPROVAL_REQUIRED:'))
    ?.replace('BROKER_APPROVAL_REQUIRED:', '')
    .trim();

  // "2026 TGTC 7610.10.00.00.19: <tanım>" → yalnız tanım
  const officialText = (decision.official_statute_text || '')
    .replace(/^2026 TGTC [\d.]+:\s*/, '')
    .split(' > ')
    .map((part) => part.replace(/^[\s\-–—]+/, '').trim())
    .filter(Boolean)
    .join(' > ');
  const steps = decision.selection_rationale || [];
  const sources = decision.legal_sources || [];
  const rules = sources.filter((s) => ['GIR', 'BOLUM_NOTU', 'FASIL_NOTU'].includes(s.source_type));
  const precedents = [
    ...(decision.precedent_btbs || []).map((p) => ({ ref: p.btb_no, code: p.gtip_code, text: p.product_description, sim: p.similarity_score, kind: 'BTB' })),
    ...(decision.precedent_ebtis || []).map((p) => ({ ref: p.reference_no, code: p.cn_code, text: p.product_description, sim: p.similarity_score, kind: `EBTI ${p.country}` })),
  ];

  const handleCopy = () => {
    navigator.clipboard.writeText(decision.gtip_code);
    addToast('GTİP kodu panoya kopyalandı.', 'success');
  };

  return (
    <div className="glass-panel" style={{
      padding: '28px',
      marginBottom: '24px',
      border: `1.5px solid ${needsReview ? 'var(--status-amber-border)' : 'var(--status-emerald-border)'}`,
      background: 'var(--bg-surface)',
    }}>

      {/* Karar */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px', color: needsReview ? 'var(--status-amber)' : 'var(--status-emerald)', fontWeight: 700, fontSize: '0.86rem' }}>
          {needsReview ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
          <span>{needsReview ? 'Müşavir incelemesi önerilir' : 'Resmî tarifede doğrulandı'}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <h2 className="font-mono" style={{ fontSize: '2.2rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '1px', margin: 0 }}>
            {decision.gtip_code}
          </h2>
          <button onClick={handleCopy} className="btn-secondary" style={{ padding: '6px 12px', fontSize: '0.78rem', gap: '5px' }} title="GTİP kodunu kopyala">
            <Copy size={14} /><span>Kopyala</span>
          </button>
          <a href={getPDFReportUrl(decision.session_id)} target="_blank" rel="noopener noreferrer" className="btn-secondary"
            style={{ padding: '6px 12px', fontSize: '0.78rem', gap: '5px', textDecoration: 'none', display: 'inline-flex', alignItems: 'center' }}>
            <Download size={14} /><span>PDF</span>
          </a>
        </div>

        {officialText && (
          <p style={{ fontSize: '0.92rem', color: 'var(--text-secondary)', margin: '10px 0 0', lineHeight: 1.5 }}>{officialText}</p>
        )}

        {(decision.evidence_summary || reviewNote) && (
          <div style={{ marginTop: '14px', padding: '10px 14px', borderRadius: '10px', background: 'var(--bg-surface-subtle)', border: '1px solid var(--border-subtle)', fontSize: '0.84rem', lineHeight: 1.5, color: 'var(--text-secondary)' }}>
            {decision.evidence_summary && <div>{decision.evidence_summary}</div>}
            {reviewNote && reviewNote !== decision.evidence_summary && (
              <div style={{ color: 'var(--status-amber)', marginTop: decision.evidence_summary ? '4px' : 0 }}>{reviewNote}</div>
            )}
          </div>
        )}
      </div>

      <ProductProfile profile={decision.product_profile} />

      {/* Neden bu kod? */}
      <div style={{ marginBottom: '24px' }}>
        <h4 style={sectionTitle}><ChevronRight size={18} color="var(--accent-blue)" />Neden bu kod?</h4>

        {steps.length > 0 ? (
          <ol style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {steps.map((step, idx) => {
              const points = step.reasoning_points?.length ? step.reasoning_points : [SOURCE_NOTES[step.source]].filter(Boolean);
              const badge = SOURCE_BADGES[step.source];
              return (
                <li key={idx} style={{ borderLeft: '3px solid var(--accent-blue)', padding: '4px 0 4px 14px' }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', flexWrap: 'wrap' }}>
                    <span style={{ ...muted, fontWeight: 600 }}>{LEVEL_LABELS[step.level] || step.level}</span>
                    <span className="font-mono" style={{ fontWeight: 800, color: 'var(--text-primary)' }}>{formatCode(step.code)}</span>
                    {badge && (
                      <span style={{ fontSize: '0.7rem', fontWeight: 700, color: badge.color, display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                        {step.source === 'BROKER' && <Users size={12} />}{badge.text}
                      </span>
                    )}
                  </div>
                  {step.description && (
                    <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', margin: '2px 0 4px' }}>{step.description}</div>
                  )}
                  {points.map((point, i) => (
                    <p key={i} style={{ fontSize: '0.86rem', lineHeight: 1.55, color: 'var(--text-primary)', margin: '2px 0' }}>{point}</p>
                  ))}
                </li>
              );
            })}
          </ol>
        ) : (
          <p style={{ fontSize: '0.86rem', lineHeight: 1.6, color: 'var(--text-secondary)', whiteSpace: 'pre-line', margin: 0 }}>
            {decision.llm_reasoning_commentary || 'Bu karar için seçim gerekçesi kaydedilmemiş.'}
          </p>
        )}
      </div>

      {/* Dayanılan kurallar */}
      {rules.length > 0 && (
        <div style={{ marginBottom: '24px' }}>
          <h4 style={sectionTitle}><BookOpen size={18} color="var(--accent-blue)" />Dayanılan kurallar</h4>
          <p style={{ ...muted, margin: '-6px 0 10px' }}>Metinler resmî kayıttan alınır; model tarafından yazılmaz.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {rules.map((rule, idx) => (
              <details key={idx} style={{ border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '8px 12px', background: 'var(--bg-surface-subtle)' }}>
                <summary style={{ cursor: 'pointer', fontSize: '0.84rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                  {rule.source_type === 'GIR' ? rule.title || rule.reference_no : rule.reference_no}
                </summary>
                <p style={{ fontSize: '0.82rem', lineHeight: 1.6, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', margin: '8px 0 2px' }}>
                  {rule.excerpt}
                </p>
              </details>
            ))}
          </div>
        </div>
      )}

      {/* Emsaller */}
      {precedents.length > 0 && (
        <details style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '16px' }}>
          <summary style={{ cursor: 'pointer', fontSize: '0.88rem', fontWeight: 700, color: 'var(--text-primary)' }}>
            Emsal kararlar ({precedents.length})
            <span style={{ ...muted, fontWeight: 400, marginLeft: '8px' }}>başka kişilere verilmiş, bağlayıcı değil</span>
          </summary>
          <ul style={{ listStyle: 'none', padding: 0, margin: '12px 0 0', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {precedents.map((p, idx) => (
              <li key={idx} style={{ fontSize: '0.82rem', lineHeight: 1.5 }}>
                <span className="font-mono" style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{p.code}</span>
                <span style={{ ...muted, margin: '0 8px' }}>{p.kind} {p.ref} · benzerlik %{Math.round((p.sim || 0) * 100)}</span>
                <div style={{ color: 'var(--text-secondary)' }}>{p.text?.length > 220 ? `${p.text.slice(0, 220)}…` : p.text}</div>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
};
