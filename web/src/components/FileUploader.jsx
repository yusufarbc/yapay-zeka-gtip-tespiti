import React, { useState } from 'react';
import { Sparkles, Image as ImageIcon, FileSearch } from 'lucide-react';

export const FileUploader = ({ onStartAnalysis, isLoading }) => {
  const [description, setDescription] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);



  const handleSubmit = (e) => {
    e.preventDefault();
    if (!description.trim()) return;
    onStartAnalysis(description, selectedFile);
  };

  return (
    <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px' }}>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '8px', fontWeight: 600 }}>
            <FileSearch size={18} color="var(--text-secondary)" />
            <span>Ürün Tanımı ve Spesifikasyonu:</span>
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Ürün cinsi, hammadde oranı, kullanım amacı ve teknik detaylarını yazın (Örn: %60 Pamuk / %40 Polyester dokuma kumaş, m² ağırlığı 140 gr...)"
            rows={4}
            style={{
              width: '100%',
              background: 'var(--bg-primary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '6px',
              padding: '12px',
              color: 'var(--text-primary)',
              fontSize: '0.9rem',
              resize: 'vertical',
              outline: 'none',
              lineHeight: 1.5
            }}
          />
        </div>



        {/* Dosya Yükleme & Buton */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <label htmlFor="file-upload" style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              background: 'var(--bg-surface-subtle)',
              padding: '8px 14px',
              borderRadius: '6px',
              cursor: 'pointer',
              fontSize: '0.82rem',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              fontWeight: 500
            }}>
              <ImageIcon size={16} />
              {selectedFile ? selectedFile.name : 'Görsel / Dosya Ekle'}
            </label>
            <input
              id="file-upload"
              type="file"
              accept="image/*,.pdf"
              style={{ display: 'none' }}
              onChange={(e) => setSelectedFile(e.target.files[0])}
            />
            {selectedFile && (
              <button
                type="button"
                onClick={() => setSelectedFile(null)}
                style={{ background: 'none', border: 'none', color: '#dc2626', fontSize: '0.8rem', cursor: 'pointer', fontWeight: 600 }}
              >
                Kaldır
              </button>
            )}
          </div>

          <button type="submit" className="btn-primary" disabled={isLoading || !description.trim()}>
            <Sparkles size={16} />
            {isLoading ? 'Analiz Ediyor...' : 'GTİP Analizini Başlat'}
          </button>
        </div>
      </form>
    </div>
  );
};
