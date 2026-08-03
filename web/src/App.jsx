import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { FileUploader } from './components/FileUploader';
import { PipelineStatus } from './components/PipelineStatus';
import { HITLQuestionModal } from './components/HITLQuestionModal';
import { GTIPResultCard } from './components/GTIPResultCard';
import { AuditHistoryTable } from './components/AuditHistoryTable';
import { analyzeProduct, respondHITL, getAuditLogs } from './api/client';

export function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('gtip_theme') || 'light';
  });

  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSubmittingHITL, setIsSubmittingHITL] = useState(false);
  const [decision, setDecision] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [errorMsg, setErrorMsg] = useState(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('gtip_theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'light' ? 'dark' : 'light');
  };

  const fetchLogs = async () => {
    try {
      const data = await getAuditLogs();
      setAuditLogs(data.entries || []);
    } catch (e) {
      console.warn("Audit log yüklenemedi:", e);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, []);

  const handleStartAnalysis = async (description, file) => {
    setIsAnalyzing(true);
    setDecision(null);
    setErrorMsg(null);

    try {
      const result = await analyzeProduct(description, file);
      setDecision(result);
    } catch (err) {
      console.error(err);
      setErrorMsg(err.response?.data?.detail || "GTİP analizi sırasında beklenmeyen bir hata oluştu.");
    } finally {
      setIsAnalyzing(false);
      fetchLogs();
    }
  };

  const handleHITLRespond = async (questionId, selectedOptionId) => {
    if (!decision) return;
    setIsSubmittingHITL(true);
    setErrorMsg(null);

    try {
      const result = await respondHITL(decision.session_id, questionId, selectedOptionId);
      setDecision(result);
    } catch (err) {
      console.error(err);
      setErrorMsg("HITL yanıtı iletilirken hata oluştu.");
    } finally {
      setIsSubmittingHITL(false);
      fetchLogs();
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header theme={theme} onToggleTheme={toggleTheme} />

      <main style={{ maxWidth: '1100px', margin: '0 auto', padding: '0 20px 40px', width: '100%', flex: 1 }}>
        
        {errorMsg && (
          <div style={{ background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', padding: '14px', borderRadius: '8px', color: '#dc2626', marginBottom: '20px', fontSize: '0.9rem', fontWeight: 500 }}>
            ⚠️ {errorMsg}
          </div>
        )}

        <FileUploader onStartAnalysis={handleStartAnalysis} isLoading={isAnalyzing} />

        <PipelineStatus isAnalyzing={isAnalyzing} decision={decision} />

        {decision && decision.status === 'WAITING_FOR_USER' && (
          <HITLQuestionModal
            question={decision.hitl_question}
            onRespond={handleHITLRespond}
            isSubmitting={isSubmittingHITL}
          />
        )}

        <GTIPResultCard decision={decision} />

        <AuditHistoryTable logs={auditLogs} />

      </main>

      <footer style={{ textAlign: 'center', padding: '20px', fontSize: '0.8rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)' }}>
        GTİP Tespit ve Karar Destek Portalı
      </footer>
    </div>
  );
}

export default App;
