import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="auth-shell">
      <div className="card stack" style={{ textAlign: "center" }}>
        <h1>Page not found</h1>
        <p>The page you're looking for doesn't exist.</p>
        <Link to="/" className="btn btn-primary" style={{ alignSelf: "center" }}>
          Go home
        </Link>
      </div>
    </div>
  );
}
