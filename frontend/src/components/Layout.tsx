import { Outlet, Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";

export default function Layout() {
  const navigate = useNavigate();
  const clear = useAuthStore((s) => s.clear);

  const handleLogout = () => {
    clear();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <nav className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <Link to="/" className="text-lg font-semibold text-brand-600">
            Job Match
          </Link>
          <div className="flex items-center gap-4">
            <Link
              to="/"
              className="text-slate-600 hover:text-brand-600"
            >
              Dashboard
            </Link>
            <Link
              to="/progress"
              className="text-slate-600 hover:text-brand-600"
            >
              Progress
            </Link>
            <Link
              to="/peers"
              className="text-slate-600 hover:text-brand-600"
            >
              Peers
            </Link>
            <Link
              to="/account"
              className="text-slate-600 hover:text-brand-600"
            >
              Account
            </Link>
            <button
              type="button"
              onClick={handleLogout}
              className="rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-200"
            >
              Logout
            </button>
          </div>
        </div>
      </nav>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>
    </div>
  );
}
