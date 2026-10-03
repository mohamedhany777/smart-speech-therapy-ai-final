import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, ApiError, AUTH_EXPIRED_EVENT, getAccessToken, getRefreshToken, setTokens, clearTokens } from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.get("/auth/me");
      setUser(me);
    } catch (err) {
      // Only drop the session when the server says it is invalid. A network
      // blip or 5xx must not log the user out.
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) clearTokens();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMe();
  }, [loadMe]);

  // The API layer fires this when a token can no longer be renewed.
  useEffect(() => {
    const onExpired = () => setUser(null);
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, []);

  async function login(email, password) {
    const tokens = await api.postPublic("/auth/login", { email, password });
    setTokens(tokens);
    await loadMe();
  }

  async function register({ email, password, full_name, preferred_language }) {
    await api.postPublic("/auth/register", { email, password, full_name, preferred_language });
    await login(email, password);
  }

  async function logout() {
    // Revoke the refresh token server-side (best effort), then clear locally.
    const refresh_token = getRefreshToken();
    if (refresh_token) {
      try {
        await api.postPublic("/auth/logout", { refresh_token });
      } catch {
        /* offline / already invalid — still log out locally */
      }
    }
    clearTokens();
    setUser(null);
  }

  const roles = user?.roles || [];
  const hasRole = (role) => roles.includes(role);

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, hasRole, refresh: loadMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
