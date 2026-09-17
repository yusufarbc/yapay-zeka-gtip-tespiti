import axios from 'axios';

// Production Nginx, /api isteklerini BACKEND_ORIGIN'e proxy eder. Böylece web
// imajı ortama özel URL içermeden tekrar kullanılabilir ve tarayıcı CORS'a
// bağımlı olmaz. VITE_API_URL yalnız özel geliştirme/preview ortamları içindir.
const API_BASE_URL = (import.meta.env.VITE_API_URL || '/api/v1').replace(/\/+$/, '');

export const getAPIErrorMessage = (error, fallback) => {
  if (error.code === 'ECONNABORTED') {
    return 'Analiz beklenenden uzun sürdü ve güvenli biçimde durduruldu. Lütfen tekrar deneyin.';
  }
  const detail = error.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map(item => item.msg).filter(Boolean).join(' ') || fallback;
  }
  return error.message || fallback;
};

export const getUploadUrl = async (filename) => {
  const response = await axios.get(`${API_BASE_URL}/generate-upload-url`, {
    params: { filename }
  });
  return response.data; // { upload_url, destination }
};

export const uploadFileDirectlyToGCS = async (file, uploadUrl) => {
  await axios.put(uploadUrl, file, {
    headers: {
      'Content-Type': file.type || 'application/octet-stream'
    }
  });
};

export const analyzeProduct = async (productDescription, imageFile = null, enableInternationalResearch = false) => {
  let imageUri = null;
  
  if (imageFile) {
    const { upload_url, destination } = await getUploadUrl(imageFile.name);
    if (upload_url.includes('mock-upload')) {
      // Emulator mode / local fallback - let the backend handle it or ignore
    } else {
      await uploadFileDirectlyToGCS(imageFile, upload_url);
      imageUri = destination;
    }
  }

  // Use the JSON endpoint which accepts image_uri instead of multipart file
  const response = await axios.post(`${API_BASE_URL}/analyze-json`, {
    product_description: productDescription,
    image_uri: imageUri,
    enable_international_research: enableInternationalResearch
  }, {
    timeout: 45000
  });
  return response.data;
};

export const searchInternationalRulings = async (productText, hsCode = null, targetCountries = ['US', 'CN', 'EU']) => {
  const response = await axios.post(`${API_BASE_URL}/precedents/international-search`, {
    product_text: productText,
    hs_code: hsCode,
    target_countries: targetCountries,
    max_results: 4
  }, {
    timeout: 45000
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

export const getCustomsBTBs = async () => {
  try {
    const response = await axios.get(`${API_BASE_URL}/customs-data/btbs`, {
      params: { limit: 3000, decision_type: 'BTB' },
      timeout: 30000
    });
    return Array.isArray(response.data) ? response.data : [];
  } catch (err) {
    console.error("Error fetching BTBs:", err);
    return [];
  }
};

export const getTGTCChapters = async () => {
  const response = await axios.get(`${API_BASE_URL}/customs-data/chapters`);
  return response.data;
};

export const getTGTCRulesAndNotes = async () => {
  const response = await axios.get(`${API_BASE_URL}/customs-data/rules-and-notes`);
  return response.data;
};

export const getETLSyncStatus = async () => {
  const response = await axios.get(`${API_BASE_URL}/customs-data/sync-status`);
  return response.data;
};

export const getTGTCHeadingItems = async (headingCode) => {
  try {
    const response = await axios.get(`${API_BASE_URL}/customs-data/heading/${headingCode}`);
    return response.data?.items || [];
  } catch (err) {
    console.error(`Pozisyon ${headingCode} kalemleri çekilemedi:`, err);
    return [];
  }
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
