import React, { useState, useEffect } from 'react';
import { BookOpen, Search, Layers, Award, RefreshCw, Database, ExternalLink } from 'lucide-react';
import { getCustomsBTBs, getTGTCChapters } from '../api/client';

export const CustomsKnowledgeExplorer = () => {
  const [activeTab, setActiveTab] = useState('btbs'); // 'btbs' | 'chapters' | 'sync'
  const [btbs, setBtbs] = useState([]);
  const [chapters, setChapters] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      setIsLoading(true);
      try {
        const [btbData, chapData] = await Promise.all([
          getCustomsBTBs(),
          getTGTCChapters()
        ]);
        setBtbs(btbData || []);
        setChapters(chapData || []);
      } catch (err) {
        console.error("Gümrük mevzuat verileri çekilirken hata oluştu:", err);
      } finally {
        setIsLoading(false);
      }
    };
    loadData();
  }, []);

  const [selectedChapter, setSelectedChapter] = useState('ALL');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 20;

  const filteredBtbs = btbs.filter(b => {
    const matchesSearch = !searchTerm || 
      (b.btb_no && b.btb_no.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (b.gtip_code && b.gtip_code.includes(searchTerm)) ||
      (b.product_description && b.product_description.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (b.legal_justification && b.legal_justification.toLowerCase().includes(searchTerm.toLowerCase()));

    const matchesChap = selectedChapter === 'ALL' || b.chapter === selectedChapter;
    return matchesSearch && matchesChap;
  });

  const totalPages = Math.ceil(filteredBtbs.length / itemsPerPage) || 1;
  const paginatedBtbs = filteredBtbs.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage);

  const filteredChapters = chapters.filter(c => 
    !searchTerm || 
    c.chapter_code.includes(searchTerm) ||
    c.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px' }}>
      
      {/* Üst Başlık */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <BookOpen size={22} color="var(--primary-brand)" />
            <span>Resmi Gümrük Tarife Cetveli & BTB Veri Kütüphanesi</span>
          </h2>
          <p style={{ fontSize: '0.84rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
            Ticaret Bakanlığı ve Resmi Gazete'den canlı senkronize edilen 99 Fasıl TGTC Cetveli ve 50.000+ Emsal BTB Karar Havuzu
          </p>
        </div>

        {/* Tab Butonları */}
        <div style={{ display: 'flex', gap: '6px', background: 'var(--bg-surface-subtle)', padding: '4px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
          <button
            onClick={() => { setActiveTab('btbs'); setCurrentPage(1); }}
            style={{
              background: activeTab === 'btbs' ? 'var(--bg-surface)' : 'transparent',
              color: activeTab === 'btbs' ? 'var(--text-primary)' : 'var(--text-secondary)',
              border: activeTab === 'btbs' ? '1px solid var(--border-subtle)' : 'none',
              padding: '6px 14px',
              borderRadius: '6px',
              fontWeight: 600,
              fontSize: '0.82rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <Award size={15} />
            <span>BTB Emsal Havuzu ({btbs.length})</span>
          </button>

          <button
            onClick={() => { setActiveTab('chapters'); setCurrentPage(1); }}
            style={{
              background: activeTab === 'chapters' ? 'var(--bg-surface)' : 'transparent',
              color: activeTab === 'chapters' ? 'var(--text-primary)' : 'var(--text-secondary)',
              border: activeTab === 'chapters' ? '1px solid var(--border-subtle)' : 'none',
              padding: '6px 14px',
              borderRadius: '6px',
              fontWeight: 600,
              fontSize: '0.82rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <Layers size={15} />
            <span>TGTC 99 Fasıl & Pozisyonlar ({chapters.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('sync')}
            style={{
              background: activeTab === 'sync' ? 'var(--bg-surface)' : 'transparent',
              color: activeTab === 'sync' ? 'var(--text-primary)' : 'var(--text-secondary)',
              border: activeTab === 'sync' ? '1px solid var(--border-subtle)' : 'none',
              padding: '6px 14px',
              borderRadius: '6px',
              fontWeight: 600,
              fontSize: '0.82rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}
          >
            <RefreshCw size={15} />
            <span>ETL Senkronizasyon Durumu</span>
          </button>
        </div>
      </div>

      {/* Arama ve Filtreleme Barı */}
      {activeTab !== 'sync' && (
        <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: '240px', position: 'relative' }}>
            <Search size={16} color="var(--text-muted)" style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }} />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => { setSearchTerm(e.target.value); setCurrentPage(1); }}
              placeholder={activeTab === 'btbs' ? "BTB No, GTİP Kodu veya ürün tanımı ile canlı ara..." : "Fasıl No veya Fasıl tanımı ara (Örn: 84, Mobilya, Plastik)..."}
              style={{
                width: '100%',
                padding: '10px 12px 10px 36px',
                borderRadius: '6px',
                border: '1px solid var(--border-subtle)',
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                fontSize: '0.86rem',
                outline: 'none'
              }}
            />
          </div>

          {activeTab === 'btbs' && (
            <select
              value={selectedChapter}
              onChange={(e) => { setSelectedChapter(e.target.value); setCurrentPage(1); }}
              style={{
                padding: '10px 14px',
                borderRadius: '6px',
                border: '1px solid var(--border-subtle)',
                background: 'var(--bg-primary)',
                color: 'var(--text-primary)',
                fontSize: '0.84rem',
                fontWeight: 600,
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value="ALL">🌐 Tüm Fasıllar (Fasıl 01 - 99)</option>
              {chapters.map(c => (
                <option key={c.chapter_code} value={c.chapter_code}>
                  Fasıl {c.chapter_code} - {c.description.substring(0, 35)}...
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {/* İçerik Tabları */}
      {isLoading ? (
        <div style={{ padding: '30px', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Resmi mevzuat verileri ve BTB kararları yükleniyor...
        </div>
      ) : (
        <>
          {/* TAB 1: Emsal BTB Kararları */}
          {activeTab === 'btbs' && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', textAlign: 'left' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
                    <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>BTB No</th>
                    <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>Tarih</th>
                    <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>GTİP Kodu</th>
                    <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>Scrap Edilen Resmi Ürün Açıklaması</th>
                    <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>Mevzuat Dayanağı (GİR)</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedBtbs.map((btb, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '10px 12px', fontWeight: 700, color: 'var(--primary-brand)', fontFamily: 'monospace' }}>{btb.btb_no}</td>
                      <td style={{ padding: '10px 12px', color: 'var(--text-muted)' }}>{btb.issue_date}</td>
                      <td style={{ padding: '10px 12px', fontWeight: 800, color: 'var(--text-primary)', fontFamily: 'monospace' }}>{btb.gtip_code}</td>
                      <td style={{ padding: '10px 12px', color: 'var(--text-primary)', fontWeight: 500 }}>{btb.product_description}</td>
                      <td style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontSize: '0.78rem' }}>{btb.legal_justification}</td>
                    </tr>
                  ))}
                  {filteredBtbs.length === 0 && (
                    <tr>
                      <td colSpan={5} style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)' }}>
                        Arama kriterlerine uygun BTB kararı bulunamadı.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>

              {/* Pagination Kontrolleri */}
              {filteredBtbs.length > 0 && (
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px', padding: '10px 4px', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                  <span>
                    Gösterilen: <b>{(currentPage - 1) * itemsPerPage + 1} - {Math.min(currentPage * itemsPerPage, filteredBtbs.length)}</b> / Toplam <b>{filteredBtbs.length}</b> Kayıt
                  </span>

                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <button
                      disabled={currentPage === 1}
                      onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                      style={{
                        padding: '6px 12px',
                        borderRadius: '6px',
                        border: '1px solid var(--border-subtle)',
                        background: currentPage === 1 ? 'var(--bg-surface-subtle)' : 'var(--bg-surface)',
                        color: currentPage === 1 ? 'var(--text-muted)' : 'var(--text-primary)',
                        cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                        fontWeight: 600
                      }}
                    >
                      ← Önceki
                    </button>

                    <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                      Sayfa {currentPage} / {totalPages}
                    </span>

                    <button
                      disabled={currentPage === totalPages}
                      onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                      style={{
                        padding: '6px 12px',
                        borderRadius: '6px',
                        border: '1px solid var(--border-subtle)',
                        background: currentPage === totalPages ? 'var(--bg-surface-subtle)' : 'var(--bg-surface)',
                        color: currentPage === totalPages ? 'var(--text-muted)' : 'var(--text-primary)',
                        cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                        fontWeight: 600
                      }}
                    >
                      Sonraki →
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: TGTC 99 Fasıl */}
          {activeTab === 'chapters' && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', textAlign: 'left' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-surface-subtle)', borderBottom: '1px solid var(--border-subtle)' }}>
                    <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600, width: '100px' }}>Fasıl No</th>
                    <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>Türk Gümrük Tarife Cetveli (TGTC) Fasıl Başlığı</th>
                    <th style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontWeight: 600 }}>Mevzuat Kapsamı</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredChapters.map((chap, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '10px 12px', fontWeight: 800, color: 'var(--text-primary)', fontFamily: 'monospace', fontSize: '1rem' }}>
                        Fasıl {chap.chapter_code}
                      </td>
                      <td style={{ padding: '10px 12px', color: 'var(--text-primary)', fontWeight: 600 }}>{chap.description}</td>
                      <td style={{ padding: '10px 12px', color: 'var(--text-secondary)', fontSize: '0.78rem' }}>
                        TGTC 2026 Cetveli ve GİR Kuralları 1-6 Uyarınca Aktif Yürürlüktedir.
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* TAB 3: Canlı ETL Senkronizasyon Durumu */}
          {activeTab === 'sync' && (
            <div style={{ background: 'var(--bg-primary)', padding: '20px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px', marginBottom: '20px' }}>
                <div style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', fontWeight: 600 }}>Scraper & Pipeline Tetikleyici</span>
                  <span style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--status-emerald)', display: 'block', margin: '4px 0' }}>GCP Cloud Scheduler</span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>Her Gece 02:00 (Sunucusuz Cron Job)</span>
                </div>

                <div style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', fontWeight: 600 }}>Ham Dosya Depolama Katmanı</span>
                  <span style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', display: 'block', margin: '4px 0' }}>Cloud Storage (GCS)</span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>gs://gtip-evrak-bucket-gtip-tespit-projesi/</span>
                </div>

                <div style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', fontWeight: 600 }}>Vektör Arama & Embeddings</span>
                  <span style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--text-primary)', display: 'block', margin: '4px 0' }}>Vertex AI Vector Search</span>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)' }}>768-Dim text-embedding-005 (Streaming Upsert)</span>
                </div>
              </div>

              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                <p><b>🔍 Otomatik Canlı Veri Çekme Akışı:</b></p>
                <ul style={{ paddingLeft: '20px', marginTop: '6px' }}>
                  <li><b>Resmi Gazete Akışı:</b> <code>resmigazete.gov.tr</code> RSS ve İthalat Rejimi Kararları anlık taranır.</li>
                  <li><b>Ticaret Bakanlığı BTB Arama Portalı:</b> <code>uygulamalar.gtb.gov.tr/BTBArama</code> portalından resmi kararlar çekilir.</li>
                  <li><b>Cloud SQL Versiyonlama:</b> Eski mevzuat kodlarının <code>valid_until</code> tarihi sonlandırılarak versiyonlu kayıt tutulur.</li>
                </ul>
              </div>
            </div>
          )}
        </>
      )}

    </div>
  );
};
