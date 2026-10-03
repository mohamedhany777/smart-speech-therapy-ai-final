import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LangContext";
import { ApiError } from "../lib/api";
import WaveDivider from "../components/WaveDivider";
import ThemeToggle from "../components/ThemeToggle";

export default function Register() {
  const { register } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "", full_name: "", preferred_language: "en" });
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await register(form);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card card stack">
        <div className="row-between">
          <WaveDivider animated height={20} />
          <ThemeToggle />
        </div>
        <h1>{t("register_title")}</h1>

        {error && <div className="alert alert-danger">{error}</div>}

        <form onSubmit={handleSubmit} className="stack">
          <div className="field">
            <label htmlFor="full_name">{t("register_name")}</label>
            <input id="full_name" required value={form.full_name} onChange={(e) => update("full_name", e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="email">{t("login_email")}</label>
            <input id="email" type="email" required value={form.email} onChange={(e) => update("email", e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="password">{t("login_password")}</label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              value={form.password}
              onChange={(e) => update("password", e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="preferred_language">{t("register_language")}</label>
            <select
              id="preferred_language"
              value={form.preferred_language}
              onChange={(e) => update("preferred_language", e.target.value)}
            >
              <option value="en">English</option>
              <option value="ar">العربية</option>
            </select>
          </div>
          <button className="btn btn-primary" type="submit" disabled={submitting}>
            {submitting ? t("common_loading") : t("register_submit")}
          </button>
        </form>

        <p className="muted">
          {t("register_has_account")} <Link to="/login">{t("register_login_link")}</Link>
        </p>
      </div>
    </div>
  );
}
