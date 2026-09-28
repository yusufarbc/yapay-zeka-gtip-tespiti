import React, { useState } from 'react';
import { Sparkles, FileSearch, Paperclip, X, Link2 } from 'lucide-react';

const MAX_FILES = 3;
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];

const labelStyle = {
  display: 'block', fontSize: '0.84rem', color: 'var(--text-primary)', marginBottom: '6px', fontWeight: 600,
};
const hintStyle = { fontWeight: 400, color: 'var(--text-muted)', marginLeft: '6px' };
const inputStyle = {
  width: '100%',
  background: 'var(--bg-primary)',
  border: '1px solid var(--border-subtle)',
  borderRadius: '10px',
  padding: '11px 14px',
  color: 'var(--text-primary)',
  fontSize: '0.9rem',
  outline: 'none',
  lineHeight: 1.5,
  fontFamily: 'inherit',
};

// Yalnız eşya adı doğru karar için çoğu zaman yetersiz: "cam balkon sistemi"
// yazıldığında taşıyıcı malzeme hiç söylenmemiş olur. Alanlar müşavirin
// önerdiği sırayla ayrı ayrı toplanır; eksik kalan kararı etkileyen bilgi
// sistem tarafından sorulur.
export const ProductInputForm = ({ onStartAnalysis, isLoading }) => {
  const [productName, setProductName] = useState('');
  const [useAndFunction, setUseAndFunction] = useState('');
  const [isMachine, setIsMachine] = useState(false);
  const [material, setMaterial] = useState('');
  const [files, setFiles] = useState([]);
  const [productUrl, setProductUrl] = useState('');
  const [extra, setExtra] = useState('');
  const [fileError, setFileError] = useState('');

  const canSubmit = !isLoading && productName.trim().length >= 2;

  const handleFiles = (event) => {
    const picked = Array.from(event.target.files || []);
    event.target.value = '';
    const rejected = picked.filter((f) => !ACCEPTED.includes(f.type) || f.size > MAX_FILE_BYTES);
    const valid = picked.filter((f) => !rejected.includes(f));
    const next = [...files, ...valid].slice(0, MAX_FILES);
    setFiles(next);
    if (rejected.length) setFileError('Yalnız JPEG, PNG, WEBP veya PDF; dosya başına en çok 10 MB.');
    else if (files.length + valid.length > MAX_FILES) setFileError(`En çok ${MAX_FILES} dosya eklenebilir.`);
    else setFileError('');
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    onStartAnalysis({
      product_name: productName.trim(),
      use_and_function: useAndFunction.trim() || null,
      is_machine: isMachine,
      material: isMachine ? null : (material.trim() || null),
      product_url: productUrl.trim() || null,
      extra_description: extra.trim() || null,
    }, files);
  };

  return (
    <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px' }}>
      <form onSubmit={handleSubmit}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.95rem', color: 'var(--text-primary)', marginBottom: '16px', fontWeight: 700 }}>
          <FileSearch size={18} color="var(--accent-blue)" />
          <span>Ürün Bilgileri</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '14px', marginBottom: '14px' }}>
          <div>
            <label style={labelStyle} htmlFor="productName">Eşya adı *</label>
            <input id="productName" required minLength={2} maxLength={300} value={productName}
              onChange={(e) => setProductName(e.target.value)} placeholder="ör. Cam balkon sistemi" style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle} htmlFor="useAndFunction">Kullanım yeri ve işlevi</label>
            <input id="useAndFunction" maxLength={1000} value={useAndFunction}
              onChange={(e) => setUseAndFunction(e.target.value)} placeholder="ör. Konut balkonlarını kapatmak" style={inputStyle} />
          </div>
        </div>

        <div style={{ marginBottom: '14px' }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', fontSize: '0.86rem', color: 'var(--text-primary)', cursor: 'pointer', marginBottom: '10px' }}>
            <input type="checkbox" checked={isMachine} onChange={(e) => setIsMachine(e.target.checked)} />
            <span>Makine veya cihaz (elektrikli/elektronik alet ve parçaları dahil)</span>
          </label>
          {!isMachine && (
            <div>
              <label style={labelStyle} htmlFor="material">
                Yapıldığı malzeme<span style={hintStyle}>plastik, çelik, kauçuk vb.; parçalı ise hepsini yazın</span>
              </label>
              <input id="material" maxLength={500} value={material} onChange={(e) => setMaterial(e.target.value)}
                placeholder="ör. Alüminyum profil, temperli cam panel" style={inputStyle} />
            </div>
          )}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '14px', marginBottom: '14px' }}>
          <div>
            <span style={labelStyle}>
              Fotoğraf, katalog, broşür, teknik resim<span style={hintStyle}>en çok {MAX_FILES}; görsel veya PDF</span>
            </span>
            <label className="btn-secondary" style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', cursor: files.length >= MAX_FILES ? 'not-allowed' : 'pointer', padding: '8px 12px', fontSize: '0.82rem', opacity: files.length >= MAX_FILES ? 0.5 : 1 }}>
              <Paperclip size={14} />
              <span>Dosya ekle</span>
              <input type="file" multiple accept={ACCEPTED.join(',')} onChange={handleFiles}
                disabled={files.length >= MAX_FILES} style={{ display: 'none' }} />
            </label>
            {files.length > 0 && (
              <ul style={{ listStyle: 'none', padding: 0, margin: '8px 0 0', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {files.map((file, idx) => (
                  <li key={`${file.name}-${idx}`} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                    <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</span>
                    <button type="button" aria-label={`${file.name} dosyasını kaldır`} onClick={() => setFiles(files.filter((_, i) => i !== idx))}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'inline-flex' }}>
                      <X size={14} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {fileError && <p style={{ fontSize: '0.78rem', color: 'var(--status-amber)', margin: '6px 0 0' }}>{fileError}</p>}
          </div>
          <div>
            <label style={labelStyle} htmlFor="productUrl">
              <Link2 size={13} style={{ verticalAlign: '-2px', marginRight: '4px' }} />Ürün sayfası linki
            </label>
            <input id="productUrl" type="url" maxLength={1000} value={productUrl}
              onChange={(e) => setProductUrl(e.target.value)} placeholder="https://..." style={inputStyle} />
          </div>
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={labelStyle} htmlFor="extra">Ek açıklama<span style={hintStyle}>teknik özellikler, ölçüler, fatura tanımı</span></label>
          <textarea id="extra" maxLength={5000} rows={3} value={extra} onChange={(e) => setExtra(e.target.value)}
            placeholder="ör. 8 mm temperli cam, katlanır, 6 kanatlı" style={{ ...inputStyle, resize: 'vertical' }} />
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap', borderTop: '1px solid var(--border-subtle)', paddingTop: '16px' }}>
          <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: 0, maxWidth: '560px' }}>
            Girmediğiniz ve kararı etkileyen bir bilgi (ör. malzeme) olursa sistem varsayımda bulunur ve analizden önce size sorar.
          </p>
          <button type="submit" className="btn-primary" disabled={!canSubmit}>
            <Sparkles size={18} />
            <span>{isLoading ? 'GTİP Analiz Ediliyor...' : 'GTİP Analizini Başlat'}</span>
          </button>
        </div>
      </form>
    </div>
  );
};

export const FileUploader = ProductInputForm;
