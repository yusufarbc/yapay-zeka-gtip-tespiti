import React, { useState } from 'react';
import { HelpCircle, ArrowRight } from 'lucide-react';

export const HITLQuestionModal = ({ question, onRespond, isSubmitting }) => {
  const [selectedOpt, setSelectedOpt] = useState('');

  if (!question) return null;

  const handleSubmit = () => {
    if (!selectedOpt) return;
    onRespond(question.question_id, selectedOpt);
  };

  return (
    <div className="glass-panel" style={{
      padding: '24px',
      marginBottom: '24px',
      border: '1px solid var(--status-amber-border)',
      background: 'var(--status-amber-bg)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
        <div style={{ background: 'var(--status-amber)', padding: '8px', borderRadius: '6px', display: 'flex' }}>
          <HelpCircle size={20} color="#ffffff" />
        </div>
        <div>
          <span className="badge badge-warning">İnsan Onayı Bekleniyor (Müşavir Netleştirmesi)</span>
          <h3 style={{ fontSize: '1rem', fontWeight: 700, marginTop: '4px', color: 'var(--text-primary)' }}>
            {question.question_text}
          </h3>
        </div>
      </div>

      <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '16px' }}>
        Denetçi Ajan (Auditor Agent) seçilen GTİP tarife pozisyonunu kesinleştirmek için aşağıdaki teknik seçeneği onaylamanızı bekliyor:
      </p>

      {/* Seçenek Listesi */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '20px' }}>
        {question.options.map((opt) => {
          const isSelected = selectedOpt === opt.option_id;
          return (
            <div
              key={opt.option_id}
              onClick={() => setSelectedOpt(opt.option_id)}
              style={{
                background: 'var(--bg-surface)',
                border: isSelected ? '2px solid var(--text-primary)' : '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: '14px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                transition: 'all 0.15s ease'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '24px',
                  height: '24px',
                  borderRadius: '50%',
                  background: isSelected ? 'var(--primary-brand)' : 'var(--bg-surface-subtle)',
                  color: isSelected ? '#ffffff' : 'var(--text-primary)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  fontSize: '0.78rem'
                }}>
                  {opt.option_id}
                </div>
                <span style={{ fontSize: '0.88rem', fontWeight: 600, color: 'var(--text-primary)' }}>{opt.text}</span>
              </div>
            </div>
          );
        })}
      </div>

      <button
        onClick={handleSubmit}
        className="btn-primary"
        disabled={!selectedOpt || isSubmitting}
        style={{ width: '100%', justifyContent: 'center' }}
      >
        <span>{isSubmitting ? 'Yanıt İletiliyor...' : 'Yanıtı Gönder ve GTİP Kodu Al'}</span>
        <ArrowRight size={16} />
      </button>
    </div>
  );
};
