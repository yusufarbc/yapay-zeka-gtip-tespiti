import React, { useState } from 'react';
import { HelpCircle, ArrowRight, CheckCircle, ShieldAlert } from 'lucide-react';

export const HITLQuestionModal = ({ question, onRespond, isSubmitting }) => {
  const [selectedOpt, setSelectedOpt] = useState('');

  if (!question) return null;

  const handleSubmit = () => {
    if (!selectedOpt) return;
    onRespond(question.question_id, selectedOpt);
  };

  const getOptionBadge = (text) => {
    const cleanText = text.toUpperCase();
    if (cleanText.includes('EVET')) {
      return <span className="badge badge-success" style={{ padding: '2px 8px' }}>EVET</span>;
    } else if (cleanText.includes('HAYIR')) {
      return <span className="badge badge-warning" style={{ padding: '2px 8px' }}>HAYIR</span>;
    }
    return null;
  };

  const cleanOptionText = (text) => {
    // Strip raw prefix if concatenated (e.g., OPT_YESEVET -> EVET)
    let cleaned = text.replace(/^(OPT_[A-Z0-9_]+)+/gi, '').trim();
    if (!cleaned) cleaned = text;
    return cleaned;
  };

  return (
    <div className="glass-panel" style={{
      padding: '24px',
      marginBottom: '24px',
      border: '1.5px solid var(--status-amber-border)',
      background: 'var(--status-amber-bg)',
      boxShadow: 'var(--shadow-lg)'
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '14px', marginBottom: '16px' }}>
        <div style={{
          background: 'var(--status-amber)',
          padding: '10px',
          borderRadius: '10px',
          display: 'flex',
          boxShadow: '0 2px 8px rgba(180, 83, 9, 0.25)'
        }}>
          <ShieldAlert size={24} color="#ffffff" />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span className="badge badge-warning">İnsan Onayı Bekleniyor (Müşavir Netleştirmesi)</span>
          </div>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.4 }}>
            {question.question_text}
          </h3>
        </div>
      </div>

      <p style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', marginBottom: '18px', lineHeight: 1.5 }}>
        Denetçi Ajan (Auditor Agent) seçilen GTİP tarife pozisyonunu kesinleştirmek için aşağıdaki teknik seçeneği teyit etmenizi bekliyor:
      </p>

      {/* Seçenek Listesi */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '22px' }}>
        {question.options.map((opt, idx) => {
          const isSelected = selectedOpt === opt.option_id;
          const letter = String.fromCharCode(65 + idx); // A, B, C...
          const displayText = cleanOptionText(opt.text);
          const badge = getOptionBadge(displayText);

          return (
            <div
              key={opt.option_id}
              onClick={() => setSelectedOpt(opt.option_id)}
              style={{
                background: 'var(--bg-surface)',
                border: isSelected ? '2px solid var(--primary-brand)' : '1px solid var(--border-subtle)',
                borderRadius: '10px',
                padding: '16px 18px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
                boxShadow: isSelected ? 'var(--shadow-md)' : 'none',
                transform: isSelected ? 'translateY(-1px)' : 'none'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flex: 1 }}>
                <div style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '50%',
                  background: isSelected ? 'var(--primary-brand)' : 'var(--bg-surface-subtle)',
                  color: isSelected ? '#ffffff' : 'var(--text-secondary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  fontSize: '0.82rem',
                  transition: 'all 0.15s ease',
                  flexShrink: 0
                }}>
                  {isSelected ? <CheckCircle size={16} color="#ffffff" /> : letter}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  {badge}
                  <span style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.4 }}>
                    {displayText}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <button
        onClick={handleSubmit}
        className="btn-primary"
        disabled={!selectedOpt || isSubmitting}
        style={{
          width: '100%',
          justify: 'center',
          padding: '12px 20px',
          fontSize: '0.92rem',
          boxShadow: selectedOpt ? '0 4px 14px rgba(0, 0, 0, 0.2)' : 'none'
        }}
      >
        <span>{isSubmitting ? 'Yanıt İletiliyor...' : 'Yanıtı Gönder ve GTİP Kodu Al'}</span>
        <ArrowRight size={18} />
      </button>
    </div>
  );
};
