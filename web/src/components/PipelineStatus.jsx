import React from 'react';
import { ShieldCheck, Cpu, Filter, Database, CheckCircle2, AlertCircle } from 'lucide-react';

export const PipelineStatus = ({ isAnalyzing, decision }) => {
  if (!isAnalyzing && !decision) return null;

  const modules = [
    { id: 1, name: 'KVKK PII Maskeleme', icon: ShieldCheck, desc: 'T.C. No / VKN gizleniyor' },
    { id: 2, name: 'Gemini Multimodal Parser', icon: Cpu, desc: 'Pydantic JSON çıkarımı' },
    { id: 3, name: 'GİR Kural Motoru', icon: Filter, desc: 'Baskın hammadde & Fasıl eleme' },
    { id: 4, name: 'BTB Hybrid RAG Search', icon: Database, desc: 'Emsal kararlar (%70) & TGTC' },
    { id: 5, name: 'Auditor Agent Denetimi', icon: CheckCircle2, desc: 'Tersine şart doğrulaması' },
  ];

  return (
    <div className="glass-panel" style={{ padding: '20px', marginBottom: '24px' }}>
      <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '16px' }}>
        ⚡ backend / langgraph ajan boru hattı (live pipeline status)
      </h3>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
        {modules.map((m) => {
          const Icon = m.icon;
          const isDone = decision && !isAnalyzing;
          
          return (
            <div
              key={m.id}
              style={{
                background: isAnalyzing ? 'rgba(6, 182, 212, 0.1)' : 'rgba(255, 255, 255, 0.04)',
                border: isAnalyzing ? '1px solid var(--accent-cyan)' : '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '12px',
                padding: '14px',
                transition: 'all 0.3s ease'
              }}
              className={isAnalyzing ? 'pulse-active' : ''}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
                <Icon size={18} color={isDone ? '#10b981' : '#06b6d4'} />
                <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>{m.name}</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{m.desc}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
