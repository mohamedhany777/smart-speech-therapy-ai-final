const TOKEN_KEY = "sst_access_token";
const REFRESH_KEY = "sst_refresh_token";

// Configurable API base URL so the frontend can be deployed as a static
// site pointed at a separately-hosted backend (e.g. Render/Railway),
// without needing an nginx reverse proxy in front of it. Falls back to a
// relative path (works with the Vite dev proxy, and with the bundled
// nginx.conf's own /api/ proxy in the Docker Compose setup) when unset.
const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setTokens({ access_token, refresh_token }) {
  localStorage.setItem(TOKEN_KEY, access_token);
  if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY);
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

// Fired when the session can no longer be renewed, so AuthContext can send the
// user back to the login page instead of leaving every page erroring with 401.
export const AUTH_EXPIRED_EVENT = "sst:auth-expired";

let refreshInFlight = null;

/**
 * Exchange the refresh token for a new token pair. Shared by concurrent
 * requests (a page firing 4 requests when the access token has expired must
 * trigger ONE refresh — refresh tokens are single-use/rotating server-side, so
 * a second parallel refresh would fail and log the user out).
 */
function refreshTokens() {
  if (refreshInFlight) return refreshInFlight;
  const refresh_token = getRefreshToken();
  if (!refresh_token) return Promise.resolve(false);

  refreshInFlight = fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token }),
  })
    .then(async (resp) => {
      if (!resp.ok) return false;
      setTokens(await resp.json());
      return true;
    })
    .catch(() => false)
    .finally(() => {
      refreshInFlight = null;
    });
  return refreshInFlight;
}

function buildHeaders(isForm, auth) {
  const headers = {};
  if (!isForm) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

/**
 * Thin fetch wrapper: attaches the bearer token, transparently renews an
 * expired access token once, parses JSON, and throws a typed ApiError with the
 * backend's `detail` message on non-2xx responses so every page can show a real
 * error instead of a silent failure.
 */
async function request(path, { method = "GET", body, isForm = false, auth = true } = {}, retried = false) {
  let resp;
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      method,
      headers: buildHeaders(isForm, auth),
      body: isForm ? body : body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection and try again.", 0, null);
  }

  if (resp.status === 401 && auth && !retried && getRefreshToken()) {
    if (await refreshTokens()) return request(path, { method, body, isForm, auth }, true);
    clearTokens();
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
  }

  if (resp.status === 204) return null;

  let data = null;
  const text = await resp.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!resp.ok) {
    let detail = (data && data.detail) || resp.statusText || "Request failed";
    // FastAPI validation errors come back as a list of {loc, msg}; show them readably.
    if (Array.isArray(detail)) {
      detail = detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`.replace(/^: /, "")).join("; ");
    }
    throw new ApiError(typeof detail === "string" ? detail : JSON.stringify(detail), resp.status, data);
  }

  return data;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body }),
  patch: (path, body) => request(path, { method: "PATCH", body }),
  postForm: (path, formData) => request(path, { method: "POST", body: formData, isForm: true }),
  delete: (path) => request(path, { method: "DELETE" }),
  // Login/register don't send an existing token, but do carry no auth header need
  postPublic: (path, body) => request(path, { method: "POST", body, auth: false }),
};

export { ApiError };
