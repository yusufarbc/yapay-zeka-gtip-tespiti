import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("UI Error Caught by Boundary:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '40px', textAlign: 'center', fontFamily: 'sans-serif', maxWidth: '600px', margin: '40px auto', background: 'var(--bg-surface)', borderRadius: '12px', border: '1px solid var(--border-subtle)', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
          <h2 style={{ color: 'var(--status-rose)', marginTop: 0 }}>Beklenmeyen Bir Hata Oluştu</h2>
          <p style={{ color: 'var(--text-secondary)' }}>Arayüz bileşenlerinden biri yüklenirken teknik bir problemle karşılaştık. Bu durum geçici olabilir.</p>
          <button 
            onClick={() => window.location.reload()} 
            style={{ 
              padding: '10px 20px', 
              marginTop: '20px', 
              background: 'var(--primary-brand)', 
              color: 'white', 
              border: 'none', 
              borderRadius: '6px', 
              cursor: 'pointer',
              fontWeight: 'bold'
            }}
          >
            Sayfayı Yenile
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
