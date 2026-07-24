import React from 'react';
import { Award, FileCheck2, Download, Scale, CheckCircle2 } from 'lucide-react';
import { getPDFReportUrl } from '../api/client';

export const GTIPResultCard = ({ decision }) => {
  if (!decision || decision.status === 'WAITING_FOR_USER') return null;

  const pdfUrl = getPDFReportUrl(decision.session_id);

  return (
    <div className="glass-panel" style={{ padding: '28px', marginBottom: '24px', border: '1px solid rgba(16, 185, 129, 0.4)' }}>
      
      {/* Üst Karar Başlığı */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <span className="badge badge-success">✓ Karar Kesinleşti</span>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Oturum: {decision.session_id.substring(0, 8)}</span>
          </div>
          <h2 style={{ fontSize: '1.8rem', fontWeight: 800, color: '#fff', letterSpacing: '1px' }}>
            {decision.gtip_code}
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>12 Haneli Resmi Türk Gümrük Tarife İstatistik Pozisyonu Kodu</p>
        </div>

        {/* Güven Skoru Göstergesi */}
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '1.6rem', fontWeight: 800, color: 'var(--accent-emerald)' }}>
            %{int_score(decision.confidence_score)}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Güven Skoru (Auditor Verified)</span>
        </div>
      </div>

      {/* Hukuki Gerekçe & GİR Kuralları */}
      <div style={{ background: 'rgba(0,0,0,0.25)', padding: '16px', borderRadius: '12px', marginBottom: '20px', border: '1px solid rgba(255,255,255,0.06)' }}>
        <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--accent-cyan)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Scale size={16} />
          Resmi Mevzuat ve Gümrük Dayanağı:
        </h4>
        <p style={{ fontSize: '0.9rem', lineHeight: 1.5, color: '#e2e8f0', marginBottom: '12px' }}>
          {decision.legal_justification}
        </p>

        {decision.applied_gir_rules && decision.applied_gir_rules.length > 0 && (
          <div>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '4px' }}>Uygulanan GİR Kuralları:</span>
            <ul style={{ listStyleType: 'disc', paddingLeft: '20px', fontSize: '0.8rem', color: '#cbd5e1' }}>
              {decision.applied_gir_rules.map((rule, i) => (
                <li key={i}>{rule}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Emsal BTB Kararları Tablosu */}
      {decision.precedent_btbs && decision.precedent_btbs.length > 0 && (
        <div style={{ marginBottom: '24px' }}>
          <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Award size={16} color="var(--accent-amber)" />
            Ticaret Bakanlığı Emsal BTB Kararları (%70 Ağırlık):
          </h4>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', textAlign: 'left' }}>
              <thead>
                <tr style={{ background: 'rgba(255,255,255,0.06)', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                  <th style={{ padding: '10px' }}>BTB No</th>
                  <th style={{ padding: '10px' }}>Tarih</th>
                  <th style={{ padding: '10px' }}>Verilen GTİP</th>
                  <th style={{ padding: '10px' }}>Emsal Ürün Tanımı</th>
                </tr>
              </thead>
              <tbody>
                {decision.precedent_btbs.map((btb, idx) => (
                  <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <td style={{ padding: '10px', fontWeight: 600, color: 'var(--accent-cyan)' }}>{btb.btb_no}</td>
                    <td style={{ padding: '10px', color: 'var(--text-secondary)' }}>{btb.issue_date}</td>
                    <td style={{ padding: '10px', fontWeight: 700 }}>{btb.gtip_code}</td>
                    <td style={{ padding: '10px', color: '#cbd5e1' }}>{btb.product_description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Alt Aksiyon Butonları */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--accent-emerald)', fontSize: '0.85rem' }}>
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
          <Download size={18} />
          Resmi GTİP & BTB PDF Raporunu İndir
        </a>
      </div>

    </div>
  );
};

function int_score(score) {
  return Math.round((score || 0) * 100);
}
