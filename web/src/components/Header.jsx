import React from 'react';
import { Building2, Sun, Moon } from 'lucide-react';

export const Header = ({ theme, onToggleTheme }) => {
  return (
    <header style={{
      padding: '16px 32px',
      marginBottom: '24px',
      background: 'var(--bg-header)',
      borderBottom: '1px solid var(--border-subtle)',
      boxShadow: 'var(--shadow-panel)'
    }}>
      <div style={{ maxWidth: '1100px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        
        {/* Logo & Başlık (Siyah / Koyu Gri Kutu) */}
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
