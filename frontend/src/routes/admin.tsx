import { createFileRoute, Link, Outlet } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { clearAdminToken, errorMessage, getAdminToken, login } from "@/lib/api-client";

export const Route = createFileRoute("/admin")({
  head: () => ({
    meta: [
      { title: "Studio admin — piano lesson calendar" },
      { name: "description", content: "Manage lessons, availability, students and invoices." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: AdminLayout,
});

function AdminLayout() {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSignedIn(getAdminToken() !== null);
    setReady(true);
    const handleUnauthenticated = () => setSignedIn(false);
    window.addEventListener("piano-admin-unauthenticated", handleUnauthenticated);
    return () => window.removeEventListener("piano-admin-unauthenticated", handleUnauthenticated);
  }, []);

  if (!ready) return null;

  if (!signedIn) {
    return (
      <main className="mx-auto w-full max-w-[360px] px-6 pt-24">
        <h1 className="text-2xl">Studio admin</h1>
        <form
          className="mt-6 space-y-3"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError(null);
            try {
              await login(password);
              setSignedIn(true);
            } catch (loginError) {
              setError(errorMessage(loginError));
            } finally {
              setBusy(false);
            }
          }}
        >
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            className="w-full border border-input bg-transparent px-3 py-2 outline-none focus:border-felt"
          />
          {error && <p className="text-sm text-felt">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="w-full bg-felt px-4 py-2.5 text-felt-foreground disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <p className="text-xs text-slate">Demo password: piano</p>
        </form>
      </main>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-border">
        <div className="mx-auto flex w-full max-w-[1400px] flex-wrap items-center gap-6 px-6 py-3">
          <span className="font-display text-lg">Studio</span>
          <nav className="flex flex-wrap gap-5 text-sm">
            <NavLink to="/admin">Week</NavLink>
            <NavLink to="/admin/availability">Availability</NavLink>
            <NavLink to="/admin/students">Students</NavLink>
            <NavLink to="/admin/alerts">Alerts</NavLink>
          </nav>
          <button
            type="button"
            onClick={() => {
              clearAdminToken();
              setSignedIn(false);
            }}
            className="ml-auto text-sm text-slate underline underline-offset-4"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1400px] px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}

function NavLink({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <Link
      to={to}
      activeOptions={{ exact: to === "/admin" }}
      activeProps={{ className: "text-felt" }}
      className="text-slate hover:text-foreground"
    >
      {children}
    </Link>
  );
}
