import React from 'react';
import { Building2, Sun, Moon } from 'lucide-react';

export const Header = ({ theme, onToggleTheme, activeNav, onSelectNav }) => {
  return (
    <header style={{
      padding: '16px 32px',
      marginBottom: '24px',
      background: 'var(--bg-header)',
      borderBottom: '1px solid var(--border-subtle)',
      boxShadow: 'var(--shadow-panel)'
    }}>
      <div style={{ maxWidth: '1100px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        
        {/* Logo & Başlık */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            background: 'var(--primary-brand)',
            padding: '8px',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Building2 size={20} color="#ffffff" />
          </div>
          <div>
            <h1 style={{ fontSize: '1.15rem', fontWeight: 700, letterSpacing: '-0.3px', color: 'var(--text-primary)' }}>
              GTİP Tespit Portalı
            </h1>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              Türk Gümrük Tarife Cetveli (TGTC) Karar Destek Sistemi
            </p>
          </div>
        </div>

        {/* Ana Navigasyon Tabları */}
        <div style={{ display: 'flex', gap: '8px', background: 'var(--bg-surface-subtle)', padding: '4px', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
          <button
            onClick={() => onSelectNav('analysis')}
            style={{
              background: activeNav === 'analysis' ? 'var(--bg-surface)' : 'transparent',
              color: activeNav === 'analysis' ? 'var(--text-primary)' : 'var(--text-secondary)',
              border: activeNav === 'analysis' ? '1px solid var(--border-subtle)' : 'none',
              padding: '6px 14px',
              borderRadius: '6px',
              fontWeight: 600,
              fontSize: '0.82rem',
              cursor: 'pointer'
            }}
          >
            🔍 GTİP Analiz Portalı
          </button>
          <button
            onClick={() => onSelectNav('explorer')}
            style={{
              background: activeNav === 'explorer' ? 'var(--bg-surface)' : 'transparent',
              color: activeNav === 'explorer' ? 'var(--text-primary)' : 'var(--text-secondary)',
              border: activeNav === 'explorer' ? '1px solid var(--border-subtle)' : 'none',
              padding: '6px 14px',
              borderRadius: '6px',
              fontWeight: 600,
              fontSize: '0.82rem',
              cursor: 'pointer'
            }}
          >
            📚 Canlı Mevzuat & BTB Kütüphanesi
          </button>
        </div>

        {/* Tema Değiştirici */}
        <button
          onClick={onToggleTheme}
          className="theme-toggle-btn"
          title="Tema Değiştir"
        >
          {theme === 'dark' ? (
            <>
              <Sun size={15} color="#fbbf24" />
              <span>Açık Tema</span>
            </>
          ) : (
            <>
              <Moon size={15} color="#a1a1aa" />
              <span>Koyu Tema</span>
            </>
          )}
        </button>

      </div>
    </header>
  );
};
