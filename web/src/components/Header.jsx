import React from 'react';
import { Building2, Sun, Moon, ShieldCheck } from 'lucide-react';

export const Header = ({ theme, onToggleTheme, activeNav, onSelectNav }) => {
  return (
    <header style={{
      padding: '16px 32px',
      marginBottom: '28px',
      background: 'var(--bg-header)',
      borderBottom: '1px solid var(--border-subtle)',
      boxShadow: 'var(--shadow-sm)',
      backdropFilter: 'blur(8px)',
      position: 'sticky',
      top: 0,
      zIndex: 100
    }}>
      <div style={{ maxWidth: '1100px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        
        {/* Logo & Başlık */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            background: 'var(--primary-brand)',
            padding: '10px',
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 2px 8px rgba(0, 0, 0, 0.15)'
          }}>
            <Building2 size={22} color="#ffffff" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h1 style={{ fontSize: '1.2rem', fontWeight: 800, letterSpacing: '-0.3px', color: 'var(--text-primary)' }}>
                GTİP Karar Destek Portalı
              </h1>
              <span className="badge badge-success" style={{ fontSize: '0.7rem', padding: '2px 8px' }}>
                <ShieldCheck size={12} /> Live
              </span>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '2px' }}>
              Türk Gümrük Tarife Cetveli (TGTC) & Emsal BTB Sistemi
            </p>
          </div>
        </div>

        {/* Ana Navigasyon Tabları */}
        <div style={{
          display: 'flex',
          gap: '6px',
          background: 'var(--bg-surface-subtle)',
          padding: '4px',
          borderRadius: '10px',
          border: '1px solid var(--border-subtle)'
        }}>
          <button
            onClick={() => onSelectNav('analysis')}
            style={{
              background: activeNav === 'analysis' ? 'var(--bg-surface)' : 'transparent',
              color: activeNav === 'analysis' ? 'var(--text-primary)' : 'var(--text-secondary)',
              border: activeNav === 'analysis' ? '1px solid var(--border-subtle)' : 'none',
              padding: '8px 16px',
              borderRadius: '8px',
              fontWeight: 700,
              fontSize: '0.84rem',
              cursor: 'pointer',
              boxShadow: activeNav === 'analysis' ? 'var(--shadow-sm)' : 'none',
              transition: 'all 0.15s ease'
            }}
          >
            🔍 GTİP Analizi
          </button>
          <button
            onClick={() => onSelectNav('explorer')}
            style={{
              background: activeNav === 'explorer' ? 'var(--bg-surface)' : 'transparent',
              color: activeNav === 'explorer' ? 'var(--text-primary)' : 'var(--text-secondary)',
              border: activeNav === 'explorer' ? '1px solid var(--border-subtle)' : 'none',
              padding: '8px 16px',
              borderRadius: '8px',
              fontWeight: 700,
              fontSize: '0.84rem',
              cursor: 'pointer',
              boxShadow: activeNav === 'explorer' ? 'var(--shadow-sm)' : 'none',
              transition: 'all 0.15s ease'
            }}
          >
            📚 TGTC & BTB Kütüphanesi
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
              <Sun size={15} color="#f59e0b" />
              <span>Açık Tema</span>
            </>
          ) : (
            <>
              <Moon size={15} color="#64748b" />
              <span>Koyu Tema</span>
            </>
          )}
        </button>

      </div>
    </header>
  );
};
