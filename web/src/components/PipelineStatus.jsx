import React from 'react';
import { ShieldCheck, Cpu, Filter, Database, CheckCircle2, Award } from 'lucide-react';

export const PipelineStatus = ({ isAnalyzing }) => {
  // Analiz yapılmıyorsa teknik boru hattı kutusunu gizle (Sade, Temiz Arayüz)
  if (!isAnalyzing) return null;

  const modules = [
    { id: 1, name: '1. PII & KVKK Maskeleme', icon: ShieldCheck, desc: 'T.C. No & Vergi No Sanitization' },
    { id: 2, name: '2. Özellik Çıkarımı', icon: Cpu, desc: 'Teknik parametre & malzeme çıkarımı' },
    { id: 3, name: '3. GİR Kural Motoru', icon: Filter, desc: 'GİR 1-6 & Fasıl matrisi kontrolü' },
    { id: 4, name: '4. BTB Hybrid RAG', icon: Database, desc: '%70 Emsal BTB & %30 TGTC taraması' },
    { id: 5, name: '5. Auditor Agent Denetimi', icon: CheckCircle2, desc: 'Tersine şart & parametre doğrulaması' },
    { id: 6, name: '6. Karar & Audit Loglama', icon: Award, desc: 'Güven kapısı (%90+) & Loglama' },
  ];

  return (
    <div className="glass-panel pulse-active" style={{ padding: '20px', marginBottom: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
        <h3 style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0 }}>
          ⚡ 6 Aşamalı Ajan Karar Destek Boru Hattı (Analiz Ediliyor...)
        </h3>
        <span style={{ fontSize: '0.78rem', color: 'var(--status-emerald)', fontWeight: 600 }}>
          ● Analiz Devam Ediyor...
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
        {modules.map((m) => {
          const Icon = m.icon;
          return (
            <div
              key={m.id}
              style={{
                background: 'var(--bg-surface-subtle)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '8px',
                padding: '12px 14px',
                transition: 'all 0.2s ease'
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                <Icon size={16} color="var(--text-secondary)" />
                <span style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)' }}>{m.name}</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>{m.desc}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
};
