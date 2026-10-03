import { useTheme } from "../context/ThemeContext";

export default function ThemeToggle({ className = "btn btn-outline" }) {
  const { theme, toggleTheme } = useTheme();
  return (
    <button className={className} onClick={toggleTheme} type="button" aria-label="Toggle light/dark mode">
      {theme === "light" ? "🌙 Dark" : "☀️ Light"}
    </button>
  );
}
