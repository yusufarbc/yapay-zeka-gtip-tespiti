import React, { useState } from 'react';
import { Sparkles, Image as ImageIcon, FileSearch, Lightbulb } from 'lucide-react';

export const FileUploader = ({ onStartAnalysis, isLoading }) => {
  const [description, setDescription] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);

  const sampleTemplates = [
    { label: '🪵 Ahşap Yemek Masası / Sandalye', text: 'Ahşap malzemeden imal edilmiş ev ve yemek odası masası, sandalye' },
    { label: '🪥 Şarjlı Diş Fırçası (Motorlu)', text: 'Şarj edilebilir dahili 3.7V elektrik motorlu diş fırçası, ağırlığı 250 gram' },
    { label: '👕 Pamuklu Örme T-Shirt', text: '%60 Pamuk / %40 Polyester karışımı örme kısa kollu erkek t-shirt' },
    { label: '📱 5G Akıllı Cep Telefonu', text: '5G hücresel ağ destekli akıllı cep telefonu, 6.7 inç ekran, bataryalı' },
    { label: '🔌 Entegre Devre Çipi', text: 'Monolitik elektronik entegre devre çipi, güç yönetim PDIP kılıflı' }
  ];

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!description.trim()) return;
    onStartAnalysis(description, selectedFile);
  };

  return (
    <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px' }}>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '14px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.92rem', color: 'var(--text-primary)', marginBottom: '8px', fontWeight: 700 }}>
            <FileSearch size={18} color="var(--accent-blue)" />
            <span>Ürün Tanımı ve Teknik Özellikleri:</span>
          </label>
          
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Ürün adı, ticari tanımı, hammadde oranı veya kullanım amacını giriniz (Örn: %60 Pamuklu örme t-shirt...)"
            rows={4}
            style={{
              width: '100%',
              background: 'var(--bg-primary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '10px',
              padding: '14px',
              color: 'var(--text-primary)',
              fontSize: '0.92rem',
              resize: 'vertical',
              outline: 'none',
              lineHeight: 1.5
            }}
          />
        </div>

        {/* Hızlı Örnek Şablonlar (Müşavir Kolaylığı) */}
        <div style={{ marginBottom: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '8px', fontWeight: 600 }}>
            <Lightbulb size={14} color="var(--status-amber)" />
            <span>Örnek Ürün Seçenekleri (1-Tıkla Doldur):</span>
          </div>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {sampleTemplates.map((tmpl, i) => (
              <button
                key={i}
                type="button"
                className="template-chip"
                onClick={() => setDescription(tmpl.text)}
              >
                {tmpl.label}
              </button>
            ))}
          </div>
        </div>

        {/* Dosya Yükleme & Buton */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px', borderTop: '1px solid var(--border-subtle)', paddingTop: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <label htmlFor="file-upload" style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              background: 'var(--bg-surface-subtle)',
              padding: '9px 16px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontSize: '0.84rem',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-primary)',
              fontWeight: 600,
              transition: 'all 0.15s ease'
            }}>
              <ImageIcon size={16} color="var(--text-secondary)" />
              {selectedFile ? selectedFile.name : 'Evrak / Fatura / Görsel Ekle'}
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
            <Sparkles size={18} />
            <span>{isLoading ? 'GTİP Analiz Ediliyor...' : 'GTİP Analizini Başlat'}</span>
          </button>
        </div>
      </form>
    </div>
  );
};
