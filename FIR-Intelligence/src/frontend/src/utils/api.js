/**
 * API client for the FIR Intelligence backend.
 *
 * The backend (v2) returns a paginated envelope for /firs, nests extracted
 * entities under `entities`, and renames a few offender fields. The components
 * in this app were written against the older flat shape, so the normalisers
 * below adapt v2 responses back to it. Keeping the mapping in one place means
 * the components do not each need to know about the wire format.
 */

const API_BASE = '/api';

async function fetchJSON(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    let message = `API error: ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      /* error body was not JSON */
    }
    throw new Error(message);
  }
  return res.json();
}

/** Flatten `entities` back to top level and restore the `date_filed` name. */
function normalizeFIR(fir) {
  const entities = fir.entities || {};
  return {
    ...fir,
    date_filed: fir.date_filed ?? fir.date,
    accused: entities.accused ?? fir.accused ?? [],
    victims: entities.victims ?? fir.victims ?? [],
    location: entities.location ?? fir.location ?? null,
    modus_operandi: entities.modus_operandi ?? fir.modus_operandi ?? null,
    ipc_sections: fir.ipc_sections ?? entities.ipc_sections ?? [],
  };
}

function normalizeOffender(offender) {
  return {
    ...offender,
    name: offender.name ?? offender.primary_name,
    total_incidents: offender.total_incidents ?? offender.fir_count ?? 0,
    confidence_score: offender.confidence_score ?? offender.match_confidence ?? 0,
    linked_firs: offender.linked_firs ?? [],
    districts: offender.districts ?? [],
    stations: offender.stations ?? [],
    crime_types: offender.crime_types ?? [],
  };
}

export const api = {
  getDashboard: () => fetchJSON('/dashboard'),

  /** Returns a plain array; pass `limit`/`offset` to page through the corpus. */
  getFIRs: async (params = {}) => {
    const qs = new URLSearchParams({ limit: 200, ...params }).toString();
    const data = await fetchJSON(`/firs?${qs}`);
    const items = Array.isArray(data) ? data : data.items || [];
    return items.map(normalizeFIR);
  },

  /** The paginated envelope, for callers that need `total`/`has_more`. */
  getFIRPage: async (params = {}) => {
    const qs = new URLSearchParams({ limit: 50, offset: 0, ...params }).toString();
    const data = await fetchJSON(`/firs?${qs}`);
    return { ...data, items: (data.items || []).map(normalizeFIR) };
  },

  // FIR numbers contain slashes and the backend route is a :path parameter,
  // so the separators must survive — encodeURIComponent would break the match.
  getFIRDetail: async (firNumber) =>
    normalizeFIR(await fetchJSON(`/firs/${String(firNumber).split('/').map(encodeURIComponent).join('/')}`)),

  getRepeatOffenders: async (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    const data = await fetchJSON(`/repeat-offenders${qs ? `?${qs}` : ''}`);
    return data.map(normalizeOffender);
  },

  getStations: () => fetchJSON('/stations'),
  getNetworks: () => fetchJSON('/networks'),
  getTrends: () => fetchJSON('/trends'),
  getFilters: () => fetchJSON('/filters'),
  getHealth: () => fetchJSON('/health'),
  getReport: () => fetchJSON('/report'),

  chat: (message) => fetchJSON('/chat', {
    method: 'POST',
    body: JSON.stringify({ message }),
  }),

  uploadFIRs: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/upload-firs`, { method: 'POST', body: formData });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = body?.detail;
      throw new Error(
        typeof detail === 'string' ? detail : detail?.message || `Upload error: ${res.status}`,
      );
    }
    return body;
  },
};
