// Browser traffic stays on the serving origin: Vite, the local web container,
// and the production gateway each forward /api and /health to FastAPI.
// An explicit external API override remains available for other deployments.
export const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL
  ?? (typeof window === 'undefined' ? 'http://localhost:8000' : '');
