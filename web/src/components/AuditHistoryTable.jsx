import React, { useState } from 'react';
import { History, Download, CheckSquare, Square } from 'lucide-react';
import { downloadBulkPDFReport } from '../api/client';

export const AuditHistoryTable = ({ logs }) => {
  const [selectedIds, setSelectedIds] = useState([]);
  const [isDownloading, setIsDownloading] = useState(false);

  if (!logs || logs.length === 0) return null;

  const handleToggleSelectAll = () => {
    if (selectedIds.length === logs.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(logs.map(l => l.session_id));
    }
  };

  const handleToggleSelectRow = (sessionId) => {
    if (selectedIds.includes(sessionId)) {
      setSelectedIds(selectedIds.filter(id => id !== sessionId));
    } else {
      setSelectedIds([...selectedIds, sessionId]);
    }
  };

  const handleBulkDownload = async () => {
    if (selectedIds.length === 0) return;
    setIsDownloading(true);
    try {
      await downloadBulkPDFReport(selectedIds);
    } catch (err) {
      console.error("Toplu PDF indirme hatası:", err);
      alert("Toplu PDF raporu indirilirken bir hata oluştu.");
    } finally {
      setIsDownloading(false);
    }
  };

  const allSelected = selectedIds.length === logs.length && logs.length > 0;

  return (
    <div className="glass-panel" style={{ padding: '24px' }}>
      
      {/* Üst Başlık ve Toplu İndir Butonu */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <h3 style={{ fontSize: '0.95rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-primary)' }}>
          <History size={18} color="var(--text-secondary)" />
          Önceki GTİP Sorguları ve Müşavirlik Kayıtları
        </h3>

        {selectedIds.length > 0 && (
          <button
            onClick={handleBulkDownload}
            className="btn-primary"
            disabled={isDownloading}
            style={{ fontSize: '0.82rem', padding: '8px 16px' }}
          >
            <Download size={15} />
            <span>{isDownloading ? 'Rapor Hazırlanıyor...' : `Seçilen ${selectedIds.length} Adet Raporu İndir (PDF)`}</span>
          </button>
        )}
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', textAlign: 'left' }}>
          <thead>
            <tr style={{ background: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
              <th style={{ padding: '10px 12px', width: '40px', textAlign: 'center' }}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={handleToggleSelectAll}
                  style={{ cursor: 'pointer', width: '16px', height: '16px', accentColor: 'var(--primary-brand)' }}
                  title="Tümünü Seç / Kaldır"
                />
              </th>
              <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>Tarih / Saat</th>
              <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>İşlem Yapan</th>
              <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>Ürün Detayı</th>
              <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>Onaylanan GTİP</th>
              <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>Güven Skoru</th>
              <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>HITL Durumu</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log, idx) => {
              const isSelected = selectedIds.includes(log.session_id);
              return (
                <tr
                  key={idx}
                  onClick={() => handleToggleSelectRow(log.session_id)}
                  style={{
                    borderBottom: '1px solid var(--border-subtle)',
                    background: isSelected ? 'var(--bg-surface-subtle)' : 'transparent',
                    cursor: 'pointer',
                    transition: 'background 0.15s ease'
                  }}
                >
                  <td style={{ padding: '10px 12px', textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => handleToggleSelectRow(log.session_id)}
                      style={{ cursor: 'pointer', width: '16px', height: '16px', accentColor: 'var(--primary-brand)' }}
                    />
                  </td>
                  <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>{new Date(log.timestamp).toLocaleString('tr-TR')}</td>
                  <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>{log.user_email}</td>
                  <td style={{ padding: '10px 12px', color: 'var(--text-primary)' }}>{log.product_name}</td>
                  <td style={{ padding: '10px 12px', fontWeight: 700, color: 'var(--text-primary)' }}>{log.final_gtip_approved}</td>
                  <td style={{ padding: '10px 12px', fontWeight: 600, color: 'var(--status-emerald)' }}>%{Math.round(log.confidence_score * 100)}</td>
                  <td style={{ padding: '10px 12px' }}>
                    {log.is_hitl_triggered ? (
                      <span className="badge badge-warning">Evet</span>
                    ) : (
                      <span className="badge badge-success">Otomatik</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
