import React from 'react';
import { History, FileText, CheckCircle2, AlertTriangle } from 'lucide-react';

export const AuditHistoryTable = ({ logs }) => {
  if (!logs || logs.length === 0) return null;

  return (
    <div className="glass-panel" style={{ padding: '24px' }}>
      <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <History size={18} color="var(--accent-indigo)" />
        Müşavirlik Onay ve Audit Kayıtları (Continuous Learning Log)
      </h3>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', textAlign: 'left' }}>
          <thead>
            <tr style={{ background: 'rgba(255,255,255,0.06)', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
              <th style={{ padding: '10px' }}>Tarih / Zaman</th>
              <th style={{ padding: '10px' }}>Müşavir</th>
              <th style={{ padding: '10px' }}>Ürün Metni</th>
              <th style={{ padding: '10px' }}>Onaylanan GTİP</th>
              <th style={{ padding: '10px' }}>Güven</th>
              <th style={{ padding: '10px' }}>HITL</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log, idx) => (
              <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <td style={{ padding: '10px', color: 'var(--text-secondary)' }}>{new Date(log.timestamp).toLocaleString('tr-TR')}</td>
                <td style={{ padding: '10px' }}>{log.user_email}</td>
                <td style={{ padding: '10px', color: '#cbd5e1' }}>{log.product_name}</td>
                <td style={{ padding: '10px', fontWeight: 700, color: 'var(--accent-cyan)' }}>{log.final_gtip_approved}</td>
                <td style={{ padding: '10px', fontWeight: 600, color: 'var(--accent-emerald)' }}>%{Math.round(log.confidence_score * 100)}</td>
                <td style={{ padding: '10px' }}>
                  {log.is_hitl_triggered ? (
                    <span className="badge badge-warning">Evet</span>
                  ) : (
                    <span className="badge badge-success">Otomatik</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
