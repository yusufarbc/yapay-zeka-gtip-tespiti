import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  BookOpen, Search, Layers, Award, RefreshCw,
  ExternalLink, CheckCircle2, Play, ChevronRight, ChevronDown,
  FileText, Scale, AlertCircle, Loader2
} from 'lucide-react';
import {
  getCustomsBTBs, getTGTCChapters, getETLSyncStatus,
  triggerETLSync, getTGTCRulesAndNotes, getTGTCHeadingItems
} from '../api/client';

// ─── helpers ────────────────────────────────────────────────────────────────

const TAB_BTN = (active) => ({
  background: active ? 'var(--bg-surface)' : 'transparent',
  color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
  border: active ? '1px solid var(--border-subtle)' : 'none',
  padding: '6px 12px',
  borderRadius: '6px',
  fontWeight: 600,
  fontSize: '0.80rem',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  gap: '5px',
  whiteSpace: 'nowrap',
});

function SkeletonRows({ n = 5 }) {
  return (
    <>
      {Array.from({ length: n }).map((_, i) => (
        <div key={i} style={{
          height: '44px',
          background: 'linear-gradient(90deg, var(--bg-surface) 25%, var(--bg-surface-subtle) 50%, var(--bg-surface) 75%)',
          backgroundSize: '200% 100%',
          animation: 'skLoad 1.5s infinite linear',
          borderRadius: '7px',
          marginBottom: '9px',
        }} />
      ))}
    </>
  );
}

function isCleanBTB(btb) {
  if (!btb) return false;
  const no = String(btb.btb_no || '');
  if (no.startsWith('TGTC2026-') || no.startsWith('TGTC-FASIL') || no.startsWith('MEVZUAT')) return false;
  
  const gtip = String(btb.gtip_code || '').replace(/\./g, '').trim();
  if (!gtip || gtip.length < 4 || !/^\d+$/.test(gtip)) return false;
  
  const desc = String(btb.product_description || '').trim();
  const descLower = desc.toLowerCase();
  
  // Harf sayısı kontrolü (Rakam/bütçe tablolarını eler)
  const letterCount = (desc.match(/[a-zA-ZçğıöşüÇĞİÖŞÜ]/g) || []).length;
  if (letterCount < 5) return false;
  
  // Kirli/Hatalı Resmî Gazete kazıma kalıpları
  if (descLower.startsWith('toplam') || descLower.startsWith('rg-pdf')) return false;
  
  const bad = ['profesör', 'maaş', 'ücret', 'matematik', 'doçent', 'lisans mezunu',
    'doktora', 'akademik', 'ders saat', 'öğrenci', 'akademisyen', 'aylık net'];
  if (bad.some(k => descLower.includes(k))) return false;
  
  return true;
}

// ─── 3. Seviye: GTİP Kalem Satırı ───────────────────────────────────────────

function GTIPRow({ item }) {
  const indent = Math.max(0, (item.digits - 4) / 2);
  const indentPx = 16 + indent * 12;
  const isLeaf = item.digits >= 10;

  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: '8px',
      padding: `5px 12px 5px ${indentPx + 40}px`,
      borderBottom: '1px solid rgba(var(--border-subtle-rgb,0,0,0), 0.05)',
      transition: 'background 0.1s',
    }}
      onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-surface-subtle)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
    >
      <span style={{
        fontFamily: 'monospace', fontWeight: isLeaf ? 700 : 500,
        fontSize: isLeaf ? '0.82rem' : '0.78rem',
        color: isLeaf ? 'var(--primary-brand)' : 'var(--text-secondary)',
        minWidth: '120px', paddingTop: '2px', flexShrink: 0
      }}>
        {item.gtip_code}
      </span>
      <span style={{ fontSize: '0.79rem', color: isLeaf ? 'var(--text-primary)' : 'var(--text-secondary)', lineHeight: 1.5, flex: 1 }}>
        {item.description}
      </span>
      {item.tax_rate && (
        <span style={{ fontSize: '0.70rem', color: 'var(--text-muted)', background: 'var(--bg-surface-subtle)', padding: '1px 6px', borderRadius: '8px', flexShrink: 0, fontWeight: 600 }}>
          %{item.tax_rate}
        </span>
      )}
      {item.unit && (
        <span style={{ fontSize: '0.69rem', color: 'var(--text-muted)', flexShrink: 0 }}>
          {item.unit}
        </span>
      )}
    </div>
  );
}

// ─── 2. Seviye: Tarife Pozisyonu Accordion ───────────────────────────────────

function HeadingAccordion({ heading, search }) {
  const [isOpen, setIsOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const handleToggle = useCallback(async () => {
    if (!isOpen && !loaded) {
      setIsLoading(true);
      const data = await getTGTCHeadingItems(heading.heading_code);
      setItems(data);
      setLoaded(true);
      setIsLoading(false);
    }
    setIsOpen(prev => !prev);
  }, [isOpen, loaded, heading.heading_code]);

  useEffect(() => {
    if (search && !isOpen && !loaded) {
      const s = search.replace(/\./g, '');
      if (s.length > 4 && s.startsWith(heading.heading_code.replace(/\./g, ''))) {
        handleToggle();
      }
    }
  }, [search]);

  const filteredItems = search && items.length > 0
    ? items.filter(it =>
        it.gtip_clean.includes(search.replace(/\./g, '')) ||
        it.description.toLowerCase().includes(search.toLowerCase())
      )
    : items;

  return (
    <div style={{ borderBottom: '1px solid var(--border-subtle)' }}>
      <button
        onClick={handleToggle}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: '8px',
          padding: '7px 14px 7px 40px',
          background: isOpen ? 'rgba(99,102,241,0.05)' : 'transparent',
          border: 'none', cursor: 'pointer', textAlign: 'left', transition: 'background 0.12s',
        }}
        onMouseEnter={e => { if (!isOpen) e.currentTarget.style.background = 'var(--bg-surface-subtle)'; }}
        onMouseLeave={e => { if (!isOpen) e.currentTarget.style.background = 'transparent'; }}
      >
        {isLoading
          ? <Loader2 size={13} color="var(--primary-brand)" style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }} />
          : isOpen
            ? <ChevronDown size={13} color="var(--primary-brand)" style={{ flexShrink: 0 }} />
            : <ChevronRight size={13} color="var(--text-muted)" style={{ flexShrink: 0 }} />
        }
        <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: '0.85rem', color: 'var(--text-primary)', minWidth: '44px' }}>
          {heading.heading_code}
        </span>
        <span style={{ fontSize: '0.80rem', color: 'var(--text-secondary)', lineHeight: 1.45, flex: 1 }}>
          {heading.description}
        </span>
      </button>

      {isOpen && (
        <div style={{ background: 'rgba(0,0,0,0.015)', borderTop: '1px solid rgba(0,0,0,0.04)' }}>
          {isLoading && (
            <div style={{ padding: '10px 40px', fontSize: '0.78rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> Kalemler yükleniyor...
            </div>
          )}
          {!isLoading && filteredItems.length === 0 && (
            <div style={{ padding: '10px 40px', fontSize: '0.77rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
              {search ? `"${search}" aramasına uygun alt kalem bulunamadı.` : 'Bu pozisyon için alt kalem bulunamadı.'}
            </div>
          )}
          {!isLoading && filteredItems.map((item, i) => (
            <GTIPRow key={item.gtip_clean || i} item={item} />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Tarife Ağacı Tab ─────────────────────────────────────────────────────

function TariffTreeTab({ chapters, headings, isLoading }) {
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState({});

  const byChapter = useMemo(() => {
    const m = {};
    (headings || []).forEach(h => {
      const ch = h.chapter_code || String(h.heading_code || '').substring(0, 2);
      if (!m[ch]) m[ch] = [];
      m[ch].push(h);
    });
    return m;
  }, [headings]);

  const filteredChaps = useMemo(() => {
    if (!search) return chapters;
    const s = search.toLowerCase();
    return chapters.filter(c =>
      c.chapter_code.includes(s) ||
      String(c.description || '').toLowerCase().includes(s) ||
      (byChapter[c.chapter_code] || []).some(h =>
        h.heading_code.includes(s) || String(h.description || '').toLowerCase().includes(s)
      )
    );
  }, [chapters, search, byChapter]);

  useEffect(() => {
    if (search) {
      const o = {};
      filteredChaps.forEach(c => { o[c.chapter_code] = true; });
      setOpen(o);
    }
  }, [search, filteredChaps]);

  const toggle = code => setOpen(prev => ({ ...prev, [code]: !prev[code] }));

  if (isLoading) return <SkeletonRows n={7} />;

  return (
    <div>
      <style>{`@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
      <div style={{ position: 'relative', marginBottom: '12px' }}>
        <Search size={14} color="var(--text-muted)" style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)' }} />
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Fasıl no, pozisyon no veya tanım ara (Örn: 8471, plastik, tekstil)..."
          style={{ width: '100%', padding: '8px 10px 8px 32px', borderRadius: '6px', border: '1px solid var(--border-subtle)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: '0.84rem', outline: 'none', boxSizing: 'border-box' }} />
      </div>

      <div style={{ fontSize: '0.77rem', color: 'var(--text-secondary)', marginBottom: '10px' }}>
        <b style={{ color: 'var(--primary-brand)' }}>{filteredChaps.length}</b> fasıl &nbsp;·&nbsp;
        <b style={{ color: 'var(--primary-brand)' }}>{headings?.length || 0}</b> tarife pozisyonu
        &nbsp;<span style={{ color: 'var(--text-muted)' }}>· Pozisyona tıklayarak GTİP alt kalemlerini görüntüleyin</span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {filteredChaps.map(ch => {
          const isOpen = !!open[ch.chapter_code];
          const all = byChapter[ch.chapter_code] || [];
          const visible = search
            ? all.filter(h => h.heading_code.includes(search) || String(h.description || '').toLowerCase().includes(search.toLowerCase()))
            : all;

          return (
            <div key={ch.chapter_code} style={{ border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
              <button onClick={() => toggle(ch.chapter_code)}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: '10px',
                  padding: '10px 14px',
                  background: isOpen ? 'rgba(99,102,241,0.09)' : 'var(--bg-surface)',
                  border: 'none', cursor: 'pointer', textAlign: 'left',
                  transition: 'background 0.14s',
                  borderBottom: isOpen ? '1px solid var(--border-subtle)' : 'none'
                }}>
                {isOpen ? <ChevronDown size={15} color="var(--primary-brand)" /> : <ChevronRight size={15} color="var(--text-muted)" />}
                <span style={{ fontFamily: 'monospace', fontWeight: 800, fontSize: '1rem', color: 'var(--primary-brand)', minWidth: '30px' }}>{ch.chapter_code}</span>
                <span style={{ fontWeight: 600, fontSize: '0.84rem', color: 'var(--text-primary)', flex: 1 }}>{ch.description}</span>
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', background: 'var(--bg-surface-subtle)', padding: '2px 7px', borderRadius: '10px', fontWeight: 600 }}>
                  {all.length} pozisyon
                </span>
              </button>

              {isOpen && (
                <div style={{ background: 'var(--bg-primary)' }}>
                  {visible.length > 0 ? visible.map(h => (
                    <HeadingAccordion key={h.heading_code} heading={h} search={search} />
                  )) : (
                    <div style={{ padding: '11px 40px', fontSize: '0.79rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                      Bu fasılda "{search}" aramasına uygun pozisyon bulunamadı.
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {filteredChaps.length === 0 && (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <Search size={20} style={{ display: 'block', margin: '0 auto 8px' }} />
            "{search}" ile eşleşen fasıl veya pozisyon bulunamadı.
          </div>
        )}
      </div>
    </div>
  );
}

// ─── BTB Tab ─────────────────────────────────────────────────────────────────

function BTBTab({ btbs, chapters, isLoading }) {
  const [search, setSearch] = useState('');
  const [chapter, setChapter] = useState('ALL');
  const [page, setPage] = useState(1);
  const [expandedRow, setExpandedRow] = useState(null);
  const PER = 20;

  const clean = useMemo(() => btbs.filter(isCleanBTB), [btbs]);

  const filtered = useMemo(() => {
    const s = search.toLowerCase();
    return clean.filter(b => {
      const ms = !s || String(b.btb_no).toLowerCase().includes(s) || String(b.gtip_code).includes(s) ||
        String(b.product_description).toLowerCase().includes(s) || String(b.legal_justification).toLowerCase().includes(s);
      return ms && (chapter === 'ALL' || b.chapter === chapter);
    });
  }, [clean, search, chapter]);

  const pages = Math.max(1, Math.ceil(filtered.length / PER));
  const cur = Math.min(page, pages);
  const paged = filtered.slice((cur - 1) * PER, cur * PER);

  if (isLoading) return <SkeletonRows n={6} />;

  const toggleRow = (key) => setExpandedRow(prev => prev === key ? null : key);

  return (
    <div>
      <div style={{ display: 'flex', gap: '10px', marginBottom: '12px', flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
          <Search size={14} color="var(--text-muted)" style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)' }} />
          <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
            placeholder="BTB No, GTİP kodu veya ürün açıklaması ile ara..."
            style={{ width: '100%', padding: '8px 10px 8px 32px', borderRadius: '6px', border: '1px solid var(--border-subtle)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: '0.83rem', outline: 'none', boxSizing: 'border-box' }} />
        </div>
        <select value={chapter} onChange={e => { setChapter(e.target.value); setPage(1); }}
          style={{ padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--border-subtle)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: '0.82rem', fontWeight: 600, outline: 'none', cursor: 'pointer' }}>
          <option value="ALL">🌐 Tüm Fasıllar (01–99)</option>
          {chapters.map(c => <option key={c.chapter_code} value={c.chapter_code}>Fasıl {c.chapter_code} – {c.description?.substring(0, 30)}...</option>)}
        </select>
      </div>

      <div style={{ display: 'flex', gap: '8px', marginBottom: '10px', fontSize: '0.77rem', color: 'var(--text-secondary)', alignItems: 'center' }}>
        <span style={{ background: 'rgba(99,102,241,0.10)', color: 'var(--primary-brand)', padding: '2px 9px', borderRadius: '12px', fontWeight: 700 }}>
          {filtered.length.toLocaleString('tr-TR')} kayıt
        </span>
        {btbs.length !== clean.length && (
          <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>({btbs.length - clean.length} kirli kayıt gizlendi)</span>
        )}
        <span style={{ color: 'var(--text-muted)', fontSize: '0.72rem' }}>· Satıra tıklayarak tam açıklamayı görüntüleyin</span>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', minWidth: '800px', borderCollapse: 'collapse', fontSize: '0.80rem' }}>
          <thead>
            <tr style={{ background: 'var(--bg-surface-subtle)', borderBottom: '2px solid var(--border-subtle)' }}>
              {['BTB / RG No', 'Tarih', 'GTİP Kodu', 'Ürün Açıklaması', 'Mevzuat Dayanağı', 'Kaynak'].map(h => (
                <th key={h} style={{ padding: '9px 11px', color: 'var(--text-secondary)', fontWeight: 700, textAlign: 'left', whiteSpace: 'nowrap' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.map((b, i) => {
              const rowKey = `${b.btb_no}-${i}`;
              const isExpanded = expandedRow === rowKey;
              const desc = String(b.product_description || '');
              const legal = String(b.legal_justification || '');
              const descShort = desc.length > 120 ? desc.substring(0, 120) + '…' : desc;
              const legalShort = legal.length > 100 ? legal.substring(0, 100) + '…' : legal;

              return (
                <React.Fragment key={rowKey}>
                  <tr
                    onClick={() => toggleRow(rowKey)}
                    style={{
                      borderBottom: isExpanded ? 'none' : '1px solid var(--border-subtle)',
                      cursor: 'pointer',
                      background: isExpanded ? 'rgba(99,102,241,0.04)' : 'transparent',
                      transition: 'background 0.12s',
                    }}
                    onMouseEnter={e => { if (!isExpanded) e.currentTarget.style.background = 'var(--bg-surface-subtle)'; }}
                    onMouseLeave={e => { if (!isExpanded) e.currentTarget.style.background = 'transparent'; }}
                  >
                    <td style={{ padding: '8px 11px', fontWeight: 700, color: 'var(--primary-brand)', fontFamily: 'monospace', fontSize: '0.76rem', maxWidth: '130px', wordBreak: 'break-all' }}>{b.btb_no}</td>
                    <td style={{ padding: '8px 11px', color: 'var(--text-muted)', whiteSpace: 'nowrap', fontSize: '0.77rem' }}>{String(b.issue_date || '').substring(0, 10)}</td>
                    <td style={{ padding: '8px 11px', fontWeight: 800, color: 'var(--text-primary)', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{b.gtip_code}</td>
                    <td style={{ padding: '8px 11px', color: 'var(--text-primary)', fontWeight: 500, maxWidth: '300px' }}>
                      <div style={{ fontSize: '0.79rem', lineHeight: 1.45 }}>
                        {isExpanded ? desc : descShort}
                      </div>
                    </td>
                    <td style={{ padding: '8px 11px', color: 'var(--text-secondary)', fontSize: '0.75rem', maxWidth: '220px', lineHeight: 1.4 }}>
                      <div style={{ fontSize: '0.75rem' }}>
                        {isExpanded ? legal : legalShort}
                      </div>
                    </td>
                    <td style={{ padding: '8px 11px', textAlign: 'center', whiteSpace: 'nowrap' }}>
                      {b.source_url ? (
                        <a
                          href={b.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          title="Resmî Gazete Orijinalini Aç"
                          onClick={e => e.stopPropagation()}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: '3px',
                            fontSize: '0.72rem', fontWeight: 600,
                            color: 'var(--primary-brand)',
                            background: 'rgba(99,102,241,0.08)',
                            border: '1px solid rgba(99,102,241,0.25)',
                            borderRadius: '5px', padding: '3px 7px',
                            textDecoration: 'none', transition: 'background 0.15s'
                          }}
                          onMouseEnter={e => e.currentTarget.style.background = 'rgba(99,102,241,0.18)'}
                          onMouseLeave={e => e.currentTarget.style.background = 'rgba(99,102,241,0.08)'}
                        >
                          {b.source_url?.endsWith('.pdf') || b.source_url?.includes('.pdf') ? '📄 PDF' : '🌐 RG'}
                        </a>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.70rem' }}>—</span>
                      )}
                    </td>
                  </tr>
                  {isExpanded && (
                    <tr style={{ borderBottom: '2px solid rgba(99,102,241,0.18)', background: 'rgba(99,102,241,0.04)' }}>
                      <td colSpan={6} style={{ padding: '0 11px 12px 11px' }}>
                        <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                          {desc.length > 120 && (
                            <div style={{ flex: 1, minWidth: '220px' }}>
                              <div style={{ fontSize: '0.70rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }}>📦 Tam Ürün Açıklaması</div>
                              <div style={{ fontSize: '0.79rem', color: 'var(--text-primary)', lineHeight: 1.65, background: 'var(--bg-surface)', padding: '10px 12px', borderRadius: '6px', border: '1px solid var(--border-subtle)', whiteSpace: 'pre-wrap' }}>{desc}</div>
                            </div>
                          )}
                          {legal.length > 100 && (
                            <div style={{ flex: 1, minWidth: '220px' }}>
                              <div style={{ fontSize: '0.70rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }}>⚖️ Tam Mevzuat Dayanağı</div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', lineHeight: 1.65, background: 'var(--bg-surface)', padding: '10px 12px', borderRadius: '6px', border: '1px solid var(--border-subtle)', whiteSpace: 'pre-wrap', maxHeight: '260px', overflowY: 'auto' }}>{legal}</div>
                            </div>
                          )}
                          {b.source_url && (
                            <div style={{ width: '100%' }}>
                              <div style={{ fontSize: '0.70rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }}>🔗 Resmî Gazete Kaynağı</div>
                              <a
                                href={b.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{ fontSize: '0.76rem', color: 'var(--primary-brand)', wordBreak: 'break-all', textDecoration: 'underline' }}
                              >
                                {b.source_url}
                              </a>
                            </div>
                          )}
                        </div>
                        <div style={{ marginTop: '8px', fontSize: '0.70rem', color: 'var(--text-muted)', textAlign: 'right', cursor: 'pointer' }} onClick={() => toggleRow(rowKey)}>
                          ▲ Kapat
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
            {paged.length === 0 && (
              <tr><td colSpan={6} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
                <AlertCircle size={18} style={{ display: 'block', margin: '0 auto 6px' }} />
                Arama kriterine uygun kayıt bulunamadı.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {filtered.length > PER && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '13px', fontSize: '0.80rem', color: 'var(--text-secondary)' }}>
          <span>Gösterilen: <b>{(cur - 1) * PER + 1}–{Math.min(cur * PER, filtered.length)}</b> / Toplam <b>{filtered.length}</b></span>
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <button disabled={cur === 1} onClick={() => setPage(p => p - 1)}
              style={{ padding: '4px 10px', borderRadius: '5px', border: '1px solid var(--border-subtle)', background: cur === 1 ? 'var(--bg-surface-subtle)' : 'var(--bg-surface)', color: cur === 1 ? 'var(--text-muted)' : 'var(--text-primary)', cursor: cur === 1 ? 'not-allowed' : 'pointer', fontWeight: 600 }}>← Önceki</button>
            <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>Sayfa {cur} / {pages}</span>
            <button disabled={cur === pages} onClick={() => setPage(p => p + 1)}
              style={{ padding: '4px 10px', borderRadius: '5px', border: '1px solid var(--border-subtle)', background: cur === pages ? 'var(--bg-surface-subtle)' : 'var(--bg-surface)', color: cur === pages ? 'var(--text-muted)' : 'var(--text-primary)', cursor: cur === pages ? 'not-allowed' : 'pointer', fontWeight: 600 }}>Sonraki →</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Yorum Kuralları Tab ──────────────────────────────────────────────────

function RulesTab({ rules, isLoading }) {
  const [section, setSection] = useState('gir');
  const [search, setSearch] = useState('');
  const [openNote, setOpenNote] = useState(null);

  const gir = rules?.gir_rules || [];
  const notes = rules?.chapter_notes || [];
  const exp = rules?.explanations || [];

  const filteredGir = useMemo(() => {
    if (!search) return gir;
    const s = search.toLowerCase();
    return gir.filter(r => {
      const textVal = typeof r === 'string' ? r : (r.title || r.name || '') + ' ' + (r.text || r.content || '');
      return textVal.toLowerCase().includes(s);
    });
  }, [gir, search]);

  const filteredNotes = useMemo(() => {
    if (!search) return notes;
    const s = search.toLowerCase();
    return notes.filter(n =>
      String(n.chapter_code || n.chapter || n.fasil || '').toLowerCase().includes(s) ||
      String(n.title || n.chapter_title || '').toLowerCase().includes(s) ||
      String(n.text || n.legal_note || n.note || n.content || '').toLowerCase().includes(s)
    );
  }, [notes, search]);

  if (isLoading) return <SkeletonRows n={5} />;

  return (
    <div>
      <div style={{ display: 'flex', gap: '6px', marginBottom: '12px', flexWrap: 'wrap' }}>
        <button onClick={() => setSection('gir')} style={TAB_BTN(section === 'gir')}>
          <Scale size={13} /> GİR Yorum Kuralları ({gir.length})
        </button>
        <button onClick={() => setSection('notes')} style={TAB_BTN(section === 'notes')}>
          <FileText size={13} /> Fasıl İzahnameleri ({notes.length})
        </button>
        {exp.length > 0 && (
          <button onClick={() => setSection('exp')} style={TAB_BTN(section === 'exp')}>
            <BookOpen size={13} /> Genel Açıklamalar ({exp.length})
          </button>
        )}
      </div>

      <div style={{ position: 'relative', marginBottom: '12px' }}>
        <Search size={14} color="var(--text-muted)" style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)' }} />
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder={section === 'gir' ? 'GİR kural başlığı veya içerik ara...' : 'Fasıl no veya not içeriği ara...'}
          style={{ width: '100%', padding: '8px 10px 8px 32px', borderRadius: '6px', border: '1px solid var(--border-subtle)', background: 'var(--bg-primary)', color: 'var(--text-primary)', fontSize: '0.83rem', outline: 'none', boxSizing: 'border-box' }} />
      </div>

      {section === 'gir' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {filteredGir.length === 0 && <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)' }}>Kural bulunamadı.</div>}
          {filteredGir.map((rule, i) => {
            const isObj = typeof rule === 'object' && rule !== null;
            const ruleNum = isObj && rule.rule_number ? rule.rule_number : (i + 1);
            const title = isObj ? (rule.title || rule.name || `GİR Kural ${i + 1}`) : rule.split(':')[0];
            const text = isObj ? (rule.text || rule.content || '—') : (rule.includes(':') ? rule.split(':').slice(1).join(':').trim() : rule);
            const summary = isObj ? rule.short_summary : null;

            return (
              <div key={i} style={{ border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '11px 15px', background: 'var(--bg-surface)' }}>
                  <span style={{ background: 'var(--primary-brand)', color: '#fff', borderRadius: '50%', width: '27px', height: '27px', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: '0.79rem', flexShrink: 0 }}>
                    {ruleNum}
                  </span>
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.86rem', color: 'var(--text-primary)' }}>{title}</div>
                    {summary && <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginTop: '2px' }}>{summary}</div>}
                  </div>
                </div>
                <div style={{ padding: '13px 15px', background: 'var(--bg-primary)', fontSize: '0.81rem', color: 'var(--text-secondary)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                  {text}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {section === 'notes' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          {filteredNotes.length === 0 && <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)' }}>Not bulunamadı.</div>}
          {filteredNotes.map((note, i) => {
            const chapCode = note.chapter_code || note.chapter || note.fasil || '';
            const key = chapCode || i;
            const isOpen = openNote === key;
            const text = note.legal_note || note.text || note.note || note.content || '';
            return (
              <div key={i} style={{ border: '1px solid var(--border-subtle)', borderRadius: '7px', overflow: 'hidden' }}>
                <button onClick={() => setOpenNote(isOpen ? null : key)}
                  style={{ width: '100%', display: 'flex', alignItems: 'center', gap: '10px', padding: '9px 13px', background: isOpen ? 'rgba(99,102,241,0.07)' : 'var(--bg-surface)', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
                  {isOpen ? <ChevronDown size={14} color="var(--primary-brand)" /> : <ChevronRight size={14} color="var(--text-muted)" />}
                  <span style={{ fontFamily: 'monospace', fontWeight: 800, fontSize: '0.86rem', color: 'var(--primary-brand)', minWidth: '26px' }}>
                    {String(chapCode).padStart(2, '0')}
                  </span>
                  <span style={{ fontWeight: 600, fontSize: '0.82rem', color: 'var(--text-primary)', flex: 1 }}>
                    {note.title || note.chapter_title || `Fasıl ${chapCode} İzahnamesi ve Notları`}
                  </span>
                  {text && (
                    <span style={{ fontSize: '0.71rem', color: 'var(--text-muted)', background: 'var(--bg-surface-subtle)', padding: '2px 7px', borderRadius: '10px' }}>
                      {text.length > 200 ? `${Math.round(text.length / 100)} paragraf` : 'Not'}
                    </span>
                  )}
                </button>
                {isOpen && (
                  <div style={{ padding: '13px 15px 13px 38px', background: 'var(--bg-primary)', fontSize: '0.80rem', color: 'var(--text-secondary)', lineHeight: 1.7, whiteSpace: 'pre-wrap', borderTop: '1px solid var(--border-subtle)', maxHeight: '380px', overflowY: 'auto' }}>
                    {text || <em style={{ color: 'var(--text-muted)' }}>Bu fasıl için özel not bulunmamaktadır.</em>}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {section === 'exp' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {exp.map((item, i) => (
            <div key={i} style={{ border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
              <div style={{ padding: '11px 15px', background: 'var(--bg-surface)', fontWeight: 700, fontSize: '0.86rem', color: 'var(--text-primary)' }}>
                {item.title}
              </div>
              <div style={{ padding: '13px 15px', background: 'var(--bg-primary)', fontSize: '0.81rem', color: 'var(--text-secondary)', lineHeight: 1.7, whiteSpace: 'pre-wrap', maxHeight: '400px', overflowY: 'auto' }}>
                {item.text}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── ETL Sync Tab ─────────────────────────────────────────────────────────

function SyncTab({ syncStatus, isSyncing, onSync }) {
  return (
    <div style={{ background: 'var(--bg-primary)', padding: '18px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', flexWrap: 'wrap', gap: '12px', background: 'var(--bg-surface)', padding: '13px 16px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
        <div>
          <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block' }}>Son ETL Senkronizasyon</span>
          <span style={{ fontSize: '0.98rem', fontWeight: 800, color: 'var(--text-primary)', fontFamily: 'monospace' }}>{syncStatus?.last_sync_time || '—'}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ background: 'rgba(16,185,129,0.12)', color: '#059669', padding: '4px 10px', borderRadius: '20px', fontSize: '0.77rem', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '5px' }}>
            <CheckCircle2 size={13} /> 2/2 Boru Hattı Aktif
          </span>
          <button onClick={onSync} disabled={isSyncing}
            style={{ background: 'var(--primary-brand)', color: '#fff', border: 'none', padding: '7px 14px', borderRadius: '6px', fontWeight: 700, fontSize: '0.81rem', cursor: isSyncing ? 'not-allowed' : 'pointer', display: 'inline-flex', alignItems: 'center', gap: '6px', opacity: isSyncing ? 0.6 : 1 }}>
            <Play size={13} /> {isSyncing ? 'Çekiliyor...' : 'Senkronizasyonu Tetikle'}
          </button>
        </div>
      </div>

      <h4 style={{ fontSize: '0.90rem', fontWeight: 800, color: 'var(--text-primary)', marginBottom: '11px' }}>🔄 T.C. Resmî Mevzuat Boru Hatları:</h4>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(270px, 1fr))', gap: '12px', marginBottom: '20px' }}>
        {[
          { name: '1. T.C. Resmî Gazete – Sınıflandırma & Emsal Kararlar', url: 'https://www.resmigazete.gov.tr', method: '2020–2026 Tarama + Günlük Monitör', scope: '6 Yıl Sınıflandırma + İthalat Rejimi Tebliğleri' },
          { name: '2. 2026 T.C. TGTC Kütüphanesi & GİR İzahnameleri', url: 'https://www.ticaret.gov.tr', method: 'Yerleşik TGTC + GİR 1-6 (Offline)', scope: '964 Pozisyon • 19.704 GTİP Kodu' }
        ].map((s, i) => (
          <div key={i} style={{ background: 'var(--bg-surface)', padding: '14px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '7px' }}>
              <h5 style={{ fontSize: '0.85rem', fontWeight: 800, color: 'var(--text-primary)', margin: 0 }}>{s.name}</h5>
              <span style={{ background: '#dcfce7', color: '#15803d', padding: '2px 7px', borderRadius: '12px', fontSize: '0.69rem', fontWeight: 700, flexShrink: 0, marginLeft: '8px' }}>ACTIVE</span>
            </div>
            <div style={{ fontSize: '0.77rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              <div style={{ marginBottom: '3px' }}><span style={{ color: 'var(--text-muted)' }}>URL: </span>
                <a href={s.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--primary-brand)', fontFamily: 'monospace' }}>{s.url} <ExternalLink size={9} style={{ display: 'inline' }} /></a></div>
              <div style={{ marginBottom: '3px' }}><span style={{ color: 'var(--text-muted)' }}>Metot: </span><b>{s.method}</b></div>
              <div><span style={{ color: 'var(--text-muted)' }}>Kapsam: </span>{s.scope}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '11px' }}>
        {[
          { label: 'Pipeline Tetikleyici', value: 'GCP Cloud Scheduler', note: 'Resmî Gazete 02:00, BTB 03:00' },
          { label: 'Ham Dosya Deposu', value: 'Cloud Storage (GCS)', note: 'gs://gumruk-mevzuat-storage-us-central1/' },
          { label: 'Vektör Arama', value: 'Cloud SQL pgvector HNSW', note: '768-Dim text-embedding-005' },
        ].map((item, i) => (
          <div key={i} style={{ background: 'var(--bg-surface)', padding: '12px', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block', fontWeight: 600 }}>{item.label}</span>
            <span style={{ fontSize: '0.90rem', fontWeight: 700, color: 'var(--text-primary)', display: 'block', margin: '4px 0 3px' }}>{item.value}</span>
            <span style={{ fontSize: '0.70rem', color: 'var(--text-secondary)', fontFamily: 'monospace' }}>{item.note}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────

export const CustomsKnowledgeExplorer = () => {
  const [activeTab, setActiveTab] = useState('tree');
  const [btbs, setBtbs] = useState([]);
  const [chapters, setChapters] = useState([]);
  const [headings, setHeadings] = useState([]);
  const [rules, setRules] = useState(null);
  const [syncStatus, setSyncStatus] = useState(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setIsLoading(true);
      try {
        const [btbR, chapR, rulesR, syncR] = await Promise.allSettled([
          getCustomsBTBs(), getTGTCChapters(), getTGTCRulesAndNotes(), getETLSyncStatus()
        ]);
        if (btbR.status === 'fulfilled') setBtbs(btbR.value || []);
        if (chapR.status === 'fulfilled') {
          const d = chapR.value;
          setChapters(Array.isArray(d) ? d : (d?.chapters || []));
          setHeadings(d?.headings || []);
        }
        if (rulesR.status === 'fulfilled') setRules(rulesR.value);
        if (syncR.status === 'fulfilled') setSyncStatus(syncR.value);
      } catch (e) { console.error('Yükleme hatası:', e); }
      finally { setIsLoading(false); }
    })();
  }, []);

  const handleSync = async () => {
    setIsSyncing(true);
    try {
      await triggerETLSync();
      const [btbData, syncData] = await Promise.all([getCustomsBTBs(), getETLSyncStatus()]);
      setBtbs(btbData || []);
      setSyncStatus(syncData);
    } catch (e) { console.error('Sync err:', e); }
    finally { setIsSyncing(false); }
  };

  const cleanCount = useMemo(() => btbs.filter(isCleanBTB).length, [btbs]);

  const TABS = [
    { id: 'tree',  label: `Tarife Ağacı (${chapters.length} Fasıl)`,  icon: <Layers size={14} /> },
    { id: 'btbs',  label: `BTB Emsal (${cleanCount})`,                  icon: <Award size={14} /> },
    { id: 'rules', label: 'GİR Kuralları & İzahnameler',                icon: <Scale size={14} /> },
    { id: 'sync',  label: 'ETL Durum',                                   icon: <RefreshCw size={14} /> },
  ];

  return (
    <div className="glass-panel" style={{ padding: '22px', marginBottom: '24px' }}>
      <style>{`@keyframes skLoad{0%{background-position:200% 0}100%{background-position:-200% 0}}`}</style>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '1.18rem', fontWeight: 800, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px', margin: 0 }}>
            <BookOpen size={20} color="var(--primary-brand)" />
            Resmi Gümrük Tarife Cetveli & BTB Veri Kütüphanesi
          </h2>
          <p style={{ fontSize: '0.81rem', color: 'var(--text-secondary)', marginTop: '4px', marginBottom: 0 }}>
            2026 T.C. TGTC (964 Pozisyon · 19.704 GTİP) + GİR Kuralları + Resmî Gazete Emsal Havuzu
          </p>
        </div>
        <div style={{ display: 'flex', gap: '4px', background: 'var(--bg-surface-subtle)', padding: '4px', borderRadius: '8px', border: '1px solid var(--border-subtle)', flexWrap: 'wrap' }}>
          {TABS.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)} style={TAB_BTN(activeTab === t.id)}>
              {t.icon} <span>{t.label}</span>
            </button>
          ))}
        </div>
      </div>

      {activeTab === 'tree'  && <TariffTreeTab chapters={chapters} headings={headings} isLoading={isLoading} />}
      {activeTab === 'btbs'  && <BTBTab btbs={btbs} chapters={chapters} isLoading={isLoading} />}
      {activeTab === 'rules' && <RulesTab rules={rules} isLoading={isLoading} />}
      {activeTab === 'sync'  && <SyncTab syncStatus={syncStatus} isSyncing={isSyncing} onSync={handleSync} />}
    </div>
  );
};
