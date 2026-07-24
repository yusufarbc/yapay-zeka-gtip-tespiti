import React, { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { FileUploader } from './components/FileUploader';
import { PipelineStatus } from './components/PipelineStatus';
import { HITLQuestionModal } from './components/HITLQuestionModal';
import { GTIPResultCard } from './components/GTIPResultCard';
import { AuditHistoryTable } from './components/AuditHistoryTable';
import { analyzeProduct, respondHITL, getAuditLogs } from './api/client';

export function App() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSubmittingHITL, setIsSubmittingHITL] = useState(false);
  const [decision, setDecision] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [errorMsg, setErrorMsg] = useState(null);

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
      <Header />

      <main style={{ maxWidth: '1100px', margin: '0 auto', padding: '0 20px 40px', width: '100%', flex: 1 }}>
        
        {errorMsg && (
          <div style={{ background: 'rgba(244, 63, 94, 0.15)', border: '1px solid rgba(244, 63, 94, 0.4)', padding: '14px', borderRadius: '10px', color: '#f43f5e', marginBottom: '20px', fontSize: '0.9rem' }}>
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

      <footer style={{ textAlign: 'center', padding: '20px', fontSize: '0.8rem', color: 'var(--text-secondary)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
        GTİP Tespit ve Karar Destek Sistemi • Powered by GCP Cloud Run, Vertex AI & LangGraph
      </footer>
    </div>
  );
}

export default App;
