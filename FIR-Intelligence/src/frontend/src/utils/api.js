const API_BASE = '/api';

async function fetchJSON(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  getDashboard: () => fetchJSON('/dashboard'),
  getFIRs: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return fetchJSON(`/firs${qs ? '?' + qs : ''}`);
  },
  getFIRDetail: (firNumber) => fetchJSON(`/firs/${encodeURIComponent(firNumber)}`),
  getRepeatOffenders: () => fetchJSON('/repeat-offenders'),
  getStations: () => fetchJSON('/stations'),
  getNetworks: () => fetchJSON('/networks'),
  getTrends: () => fetchJSON('/trends'),
  getReport: () => fetchJSON('/report'),
  chat: (message) => fetchJSON('/chat', {
    method: 'POST',
    body: JSON.stringify({ message }),
  }),
  uploadFIRs: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/upload-firs`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) throw new Error(`Upload error: ${res.status}`);
    return res.json();
  },
};
