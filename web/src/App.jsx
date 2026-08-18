import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { FileUploader } from './components/FileUploader';
import { HITLQuestionModal } from './components/HITLQuestionModal';
import { GTIPResultCard } from './components/GTIPResultCard';
import { AuditHistoryTable } from './components/AuditHistoryTable';
import { CustomsKnowledgeExplorer } from './components/CustomsKnowledgeExplorer';
import ErrorBoundary from './components/ErrorBoundary';
import { SkeletonLoader } from './components/SkeletonLoader';
import { PipelineStatus } from './components/PipelineStatus';
import { analyzeProduct, respondHITL, getAuditLogs } from './api/client';
import { useToast } from './components/ToastContext';

export function App() {
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('gtip_theme') || 'light';
  });

  const [activeNav, setActiveNav] = useState('analysis'); // 'analysis' | 'explorer'
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSubmittingHITL, setIsSubmittingHITL] = useState(false);
  const [decision, setDecision] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const { addToast } = useToast();

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

  const handleStartAnalysis = async (description) => {
    setIsAnalyzing(true);
    setDecision(null);

    try {
      const result = await analyzeProduct(description);
      setDecision(result);
    } catch (err) {
      console.error(err);
      addToast(err.response?.data?.detail || err.message || "GTİP analizi sırasında beklenmeyen bir hata oluştu.", "error");
    } finally {
      setIsAnalyzing(false);
      fetchLogs();
    }
  };

  const handleHITLRespond = async (questionId, selectedOptionId) => {
    if (!decision) return;
    setIsSubmittingHITL(true);

    try {
      const result = await respondHITL(decision.session_id, questionId, selectedOptionId);
      setDecision(result);
    } catch (err) {
      console.error(err);
      addToast(err.response?.data?.detail || err.message || "Müşavir teyit yanıtı iletilirken hata oluştu.", "error");
    } finally {
      setIsSubmittingHITL(false);
      fetchLogs();
    }
  };

  return (
    <ErrorBoundary>
      <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        <Header theme={theme} onToggleTheme={toggleTheme} activeNav={activeNav} onSelectNav={setActiveNav} />

        <main style={{ maxWidth: activeNav === 'explorer' ? '1540px' : '1100px', margin: '0 auto', padding: '0 24px 40px', width: '100%', flex: 1, transition: 'max-width 0.3s ease' }}>

          {activeNav === 'analysis' ? (
            <>
              <FileUploader onStartAnalysis={handleStartAnalysis} isLoading={isAnalyzing} />

              {isAnalyzing && (
                <>
                  <PipelineStatus isAnalyzing={isAnalyzing} />
                  <SkeletonLoader />
                </>
              )}

              {/* Müşavir Teyidi Bekleyen Durumda Sadece Soru Kartı Gösterilir */}
              {decision && decision.status === 'WAITING_FOR_USER' && (
                <HITLQuestionModal
                  question={decision.hitl_question}
                  onRespond={handleHITLRespond}
                  isSubmitting={isSubmittingHITL}
                />
              )}

              {/* Karar Kesinleştiğinde Sonuç Kartı Gösterilir */}
              {decision && decision.status === 'COMPLETED' && (
                <GTIPResultCard decision={decision} />
              )}

              <AuditHistoryTable logs={auditLogs} />
            </>
          ) : (
            <CustomsKnowledgeExplorer />
          )}

        </main>

        <footer style={{ textAlign: 'center', padding: '20px', fontSize: '0.82rem', color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)' }}>
          Türk Gümrük Tarife Cetveli (TGTC) Karar Destek Portalı • Kurumsal Müşavir Sürümü
        </footer>
      </div>
    </ErrorBoundary>
  );
}

export default App;
