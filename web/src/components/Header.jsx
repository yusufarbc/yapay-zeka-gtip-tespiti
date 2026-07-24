import React from 'react';
import { ShieldCheck, Cpu, Globe, Lock } from 'lucide-react';

export const Header = () => {
  return (
    <header className="glass-panel" style={{ padding: '16px 32px', marginBottom: '24px', borderRadius: '0 0 16px 16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        
        {/* Sol Logo & Başlık */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            background: 'linear-gradient(135deg, #06b6d4, #3b82f6)',
            padding: '10px',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Cpu size={26} color="#fff" />
          </div>
          <div>
            <h1 style={{ fontSize: '1.25rem', fontWeight: 700, letterSpacing: '-0.5px' }}>
              GTİP Tespit & Karar Destek Portalı
            </h1>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Kıdemli Müşavir Yardımcısı • GCP Serverless & Gemini 2.5 Flash
            </p>
          </div>
        </div>

        {/* Sağ Rozetler & Sistem Bilgisi */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', background: 'rgba(255,255,255,0.05)', padding: '6px 12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)' }}>
            <Globe size={14} color="#06b6d4" />
            <span>Region: <b>europe-west3 (Frankfurt)</b></span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', background: 'rgba(16, 185, 129, 0.1)', padding: '6px 12px', borderRadius: '8px', border: '1px solid rgba(16, 185, 129, 0.3)', color: '#10b981' }}>
            <Lock size={14} />
            <span>KVKK Pre-LLM Masking Active</span>
          </div>

          <span className="badge badge-info">GCP Serverless</span>
        </div>

      </div>
    </header>
  );
};
