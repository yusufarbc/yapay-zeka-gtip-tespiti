import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api/v1';

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
