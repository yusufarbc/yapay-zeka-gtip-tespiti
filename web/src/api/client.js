import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://gtip-api-230333256951.europe-west3.run.app/api/v1';

export const analyzeProduct = async (productDescription, file = null) => {
  const formData = new FormData();
  formData.append('product_description', productDescription);
  if (file) {
    formData.append('image', file);
  }

  const response = await axios.post(`${API_BASE_URL}/analyze`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

export const respondHITL = async (sessionId, questionId, selectedOptionId, customNote = '') => {
  const response = await axios.post(`${API_BASE_URL}/hitl/respond`, {
    session_id: sessionId,
    question_id: questionId,
    selected_option_id: selectedOptionId,
    custom_note: customNote,
  });
  return response.data;
};

export const getAuditLogs = async () => {
  const response = await axios.get(`${API_BASE_URL}/audit/logs`);
  return response.data;
};

export const getPDFReportUrl = (sessionId) => {
  return `${API_BASE_URL}/report/pdf/${sessionId}`;
};

export const downloadBulkPDFReport = async (sessionIds) => {
  const response = await axios.post(`${API_BASE_URL}/report/pdf/bulk`, {
    session_ids: sessionIds,
  }, {
    responseType: 'blob'
  });
  
  const blob = new Blob([response.data], { type: 'application/pdf' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', `toplu_gtip_raporu_${sessionIds.length}_adet.pdf`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};
