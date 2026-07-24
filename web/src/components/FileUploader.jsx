import React, { useState } from 'react';
import { UploadCloud, FileText, Sparkles, Image as ImageIcon } from 'lucide-react';

export const FileUploader = ({ onStartAnalysis, isLoading }) => {
  const [description, setDescription] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);

  const handleQuickSample = (text) => {
    setDescription(text);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!description.trim()) return;
    onStartAnalysis(description, selectedFile);
  };

  return (
    <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px' }}>
      <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Sparkles size={18} color="var(--accent-cyan)" />
        1. Ürün Açıklaması veya Fatura Yükleme
      </h2>

      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'block', fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '8px' }}>
            Ürün Tanımı / Fatura İçeriği / Teknik Spesifikasyon Metni:
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Örn: %60 Pamuk / %40 Polyester dokuma kumaş, m² ağırlığı 140 gram... veya Şarjlı döner başlıklı elektrikli diş fırçası..."
            rows={4}
            style={{
              width: '100%',
              background: 'rgba(0, 0, 0, 0.3)',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              borderRadius: '10px',
              padding: '12px',
              color: '#fff',
              fontSize: '0.95rem',
              resize: 'vertical',
              outline: 'none'
            }}
          />
        </div>

        {/* Hızlı Hazır Örnek Butonları */}
        <div style={{ marginBottom: '20px', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Hızlı Örnek Seç:</span>
          <button
            type="button"
            onClick={() => handleQuickSample("Şarj edilebilir dahili 3.7V elektrik motorlu, döner başlıklı diş temizleme cihazı (Şarjlı Diş Fırçası).")}
            style={{ padding: '6px 12px', borderRadius: '6px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#06b6d4', fontSize: '0.8rem', cursor: 'pointer' }}
          >
            🪥 Şarjlı Diş Fırçası (Fasıl 85)
          </button>

          <button
            type="button"
            onClick={() => handleQuickSample("%60 Pamuk / %40 Polyester karışımı dokuma kumaş. En: 150cm.")}
            style={{ padding: '6px 12px', borderRadius: '6px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#3b82f6', fontSize: '0.8rem', cursor: 'pointer' }}
          >
            🧵 %60 Pamuklu Kumaş (Fasıl 52)
          </button>

          <button
            type="button"
            onClick={() => handleQuickSample("Demontaj kutu içerisinde sökülmüş 24 vitesli iki tekerlekli bisiklet aksamları.")}
            style={{ padding: '6px 12px', borderRadius: '6px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#10b981', fontSize: '0.8rem', cursor: 'pointer' }}
          >
            🚲 Demonte Bisiklet (Fasıl 87)
          </button>
        </div>

        {/* Dosya / Fotoğraf Yükleme Alanı */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <label htmlFor="file-upload" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', background: 'rgba(255,255,255,0.08)', padding: '8px 16px', borderRadius: '8px', cursor: 'pointer', fontSize: '0.85rem', border: '1px solid rgba(255,255,255,0.15)' }}>
              <ImageIcon size={16} />
              {selectedFile ? selectedFile.name : 'Ürün Fotoğrafı / PDF Ekle'}
            </label>
            <input
              id="file-upload"
              type="file"
              accept="image/*,.pdf"
              style={{ display: 'none' }}
              onChange={(e) => setSelectedFile(e.target.files[0])}
            />
            {selectedFile && (
              <button type="button" onClick={() => setSelectedFile(null)} style={{ background: 'none', border: 'none', color: 'var(--accent-rose)', fontSize: '0.8rem', cursor: 'pointer' }}>
                Kaldır
              </button>
            )}
          </div>

          <button type="submit" className="btn-primary" disabled={isLoading || !description.trim()}>
            <Sparkles size={18} />
            {isLoading ? 'Ajanlar Analiz Ediyor...' : 'GTİP Analizini Başlat (3 sn)'}
          </button>
        </div>
      </form>
    </div>
  );
};
