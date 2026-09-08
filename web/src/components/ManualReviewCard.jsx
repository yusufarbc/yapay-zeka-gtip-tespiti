import React from 'react';
import { ShieldAlert } from 'lucide-react';

export const ManualReviewCard = ({ decision }) => (
  <section className="glass-panel" role="status" style={{
    padding: '24px', marginBottom: '24px',
    border: '1.5px solid var(--status-amber-border)',
    background: 'var(--status-amber-bg)',
  }}>
    <h2 style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '1.15rem', marginBottom: '12px' }}>
      <ShieldAlert size={24} aria-hidden="true" /> Müşavir incelemesi gerekiyor
    </h2>
    <p>GTİP kodu kesinleştirilemedi. Ürünün teknik bilgilerini ve dayanak belgelerini bir gümrük müşaviriyle değerlendirin.</p>
    {decision.gtip_code && <p style={{ marginTop: '12px' }}>İncelenecek aday kod: <strong>{decision.gtip_code}</strong></p>}
    {decision.llm_reasoning_commentary && <p style={{ marginTop: '12px' }}>{decision.llm_reasoning_commentary}</p>}
    {decision.audit_notes?.length > 0 && (
      <ul style={{ marginTop: '12px', paddingLeft: '20px' }}>
        {decision.audit_notes.map((note, index) => <li key={index}>{note}</li>)}
      </ul>
    )}
  </section>
);
