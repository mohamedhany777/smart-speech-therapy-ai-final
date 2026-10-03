import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LangContext";
import WaveDivider from "./WaveDivider";
import ThemeToggle from "./ThemeToggle";

const NAV_ITEMS = [
  { to: "/", key: "nav_dashboard", roles: null },
  { to: "/disorders", key: "nav_disorders", roles: null },
  { to: "/exercises", key: "nav_exercises", roles: null },
  { to: "/games", key: "nav_games", roles: null },
  { to: "/assessment", key: "nav_assessment", roles: null },
  { to: "/assistant", key: "nav_assistant", roles: null },
  { to: "/plans", key: "nav_plans", roles: null },
  { to: "/specialist", key: "nav_specialist", roles: ["SPECIALIST"] },
  { to: "/admin", key: "nav_admin", roles: ["ADMIN"] },
];

export default function Layout({ children }) {
  const { user, logout, hasRole } = useAuth();
  const { t, lang, toggleLang } = useLang();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">
            <WaveDivider height={22} />
          </span>
        </div>
        <div className="brand-name">{t("appName")}</div>

        <nav>
          <ul className="nav-list">
            {NAV_ITEMS.filter((item) => !item.roles || item.roles.some((r) => hasRole(r))).map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.to === "/"} className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
                  <span className="nav-label-text">{t(item.key)}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div style={{ marginTop: "auto" }} className="stack">
          <ThemeToggle />
          <button className="btn btn-outline" onClick={toggleLang} type="button">
            {lang === "en" ? "العربية" : "English"}
          </button>
          {user && (
            <div className="stack" style={{ gap: 4 }}>
              <span className="muted nav-label-text">{user.full_name || user.email}</span>
              <button className="btn btn-outline" onClick={handleLogout} type="button">
                {t("nav_logout")}
              </button>
            </div>
          )}
        </div>
      </aside>

      <main className="main-content">{children}</main>
    </div>
  );
}
