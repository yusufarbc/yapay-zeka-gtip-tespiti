import React, { useState } from 'react';
import { HelpCircle, AlertTriangle, ArrowRight } from 'lucide-react';

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
      border: '1px solid var(--accent-amber)',
      background: 'rgba(245, 158, 11, 0.08)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
        <div style={{ background: 'var(--accent-amber)', padding: '8px', borderRadius: '8px', display: 'flex' }}>
          <HelpCircle size={22} color="#000" />
        </div>
        <div>
          <span className="badge badge-warning">İnsan Onayı Bekleniyor (HITL Wait State)</span>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginTop: '4px' }}>
            {question.question_text}
          </h3>
        </div>
      </div>

      <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '16px' }}>
        Yapay zeka denetçi ajanı (Auditor Agent) seçilen GTİP kodunun şartlarını doğrulamak için aşağıdaki teknik detayı netleştirmenizi istiyor:
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
                background: isSelected ? 'rgba(6, 182, 212, 0.25)' : 'rgba(0, 0, 0, 0.3)',
                border: isSelected ? '1.5px solid var(--accent-cyan)' : '1px solid rgba(255, 255, 255, 0.12)',
                borderRadius: '10px',
                padding: '14px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                transition: 'all 0.2s ease'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '24px',
                  height: '24px',
                  borderRadius: '50%',
                  background: isSelected ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.1)',
                  color: isSelected ? '#000' : '#fff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  fontSize: '0.8rem'
                }}>
                  {opt.option_id}
                </div>
                <span style={{ fontSize: '0.9rem', fontWeight: 500 }}>{opt.text}</span>
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
        <span>{isSubmitting ? 'Yanıt İletiliyor...' : 'Yanıtı Gönder ve GTİP\'i Kesinleştir'}</span>
        <ArrowRight size={18} />
      </button>
    </div>
  );
};
