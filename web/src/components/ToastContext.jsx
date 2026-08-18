import React, { createContext, useContext, useState, useCallback } from 'react';

const ToastContext = createContext();

export const useToast = () => useContext(ToastContext);

export const ToastProvider = ({ children }) => {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = 'info', duration = 3000) => {
    const id = Date.now().toString();
    setToasts(prev => [...prev, { id, message, type }]);

    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, duration);
  }, []);

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div style={{
        position: 'fixed',
        bottom: '20px',
        right: '20px',
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        gap: '10px'
      }}>
        {toasts.map(toast => {
          const bg = toast.type === 'error' ? 'var(--status-rose-bg)' : toast.type === 'success' ? 'var(--status-emerald-bg)' : 'var(--bg-surface-subtle)';
          const color = toast.type === 'error' ? 'var(--status-rose)' : toast.type === 'success' ? 'var(--status-emerald)' : 'var(--text-primary)';
          const border = toast.type === 'error' ? 'var(--status-rose-border)' : toast.type === 'success' ? 'var(--status-emerald-border)' : 'var(--border-subtle)';

          return (
            <div key={toast.id} style={{
              background: bg,
              color: color,
              border: `1px solid ${border}`,
              padding: '12px 20px',
              borderRadius: '8px',
              boxShadow: 'var(--shadow-md)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              minWidth: '250px',
              animation: 'slideInRight 0.3s ease-out'
            }}>
              <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{toast.message}</span>
              <button 
                onClick={() => removeToast(toast.id)}
                style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '1.2rem', marginLeft: '12px' }}
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
      <style>
        {`
          @keyframes slideInRight {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
          }
        `}
      </style>
    </ToastContext.Provider>
  );
};
