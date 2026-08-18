import React, { useState } from 'react';
import { Sparkles, FileSearch } from 'lucide-react';

export const ProductInputForm = ({ onStartAnalysis, isLoading }) => {
  const [description, setDescription] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!description.trim()) return;
    onStartAnalysis(description);
  };

  return (
    <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px' }}>
      <form onSubmit={handleSubmit}>
        <div style={{ marginBottom: '16px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.92rem', color: 'var(--text-primary)', marginBottom: '8px', fontWeight: 700 }}>
            <FileSearch size={18} color="var(--accent-blue)" />
            <span>Ürün Tanımı ve Teknik Özellikleri:</span>
          </label>
          
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Ürün adı, ticari tanımı, hammadde oranı veya kullanım amacını giriniz..."
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


        {/* Buton */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', borderTop: '1px solid var(--border-subtle)', paddingTop: '16px' }}>
          <button type="submit" className="btn-primary" disabled={isLoading || !description.trim()}>
            <Sparkles size={18} />
            <span>{isLoading ? 'GTİP Analiz Ediliyor...' : 'GTİP Analizini Başlat'}</span>
          </button>
        </div>
      </form>
    </div>
  );
};

export const FileUploader = ProductInputForm;


