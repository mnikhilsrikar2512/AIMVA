import { lazy, Suspense, useState } from "react";
import { Link, NavLink, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Gauge, LogOut, ShieldCheck } from "lucide-react";
import { Button, Field, Notice, Spinner, cx } from "../components/ui";
import { post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { canSeeQuality } from "../lib/modules";

/* The AIMVA team app: its own address, its own sign-in, only the console and the quality numbers.
   The server checks the role on every request; this shell only decides what to show. */

const Console = lazy(() => import("../pages/app/Console"));
const Quality = lazy(() => import("../pages/app/Owner"));

const ROLE_LABEL = { owner: "Owner", manager: "Management", developer: "Development", support: "Support", accountant: "Accounts" };

function Loading() {
  return <div className="grid min-h-[50vh] place-items-center"><Spinner className="size-5" /></div>;
}

function Mark() {
  return (
    <span className="flex items-center gap-2 font-display text-[15px] font-bold text-strong">
      <span className="grid size-7 place-items-center rounded-lg bg-strong text-xs text-surface">A</span>
      AIMVA <span className="font-medium text-muted">Team</span>
    </span>
  );
}

function SignIn() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const d = await post("/api/auth/login", { email, password });
      setUser(d.user);
      navigate(location.state?.from || "/", { replace: true });
    } catch (err) {
      setError(err.status === 403 && err.data?.needs_verification
        ? "Verify your email first: sign in once in the AIMVA app and enter the code we send."
        : err.message);
    } finally { setBusy(false); }
  };
  return (
    <div className="grid min-h-screen place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8"><Mark /></div>
        <h1 className="text-2xl font-bold">Sign in to the team app</h1>
        <p className="mt-1.5 text-sm text-muted">For the people who run AIMVA. Customers sign in to the AIMVA app instead.</p>
        <form onSubmit={submit} className="mt-6 space-y-4">
          {error && <Notice tone="rose">{error}</Notice>}
          <Field label="Work email"><input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required autoFocus /></Field>
          <Field label="Password"><input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></Field>
          <Button type="submit" busy={busy} className="h-11 w-full">Sign in</Button>
        </form>
        <p className="mt-6 text-xs text-faint">First time? An owner adds your email on the Team tab. Create your account with that email in the AIMVA app, verify it, then sign in here. Forgot your password? Reset it in the AIMVA app.</p>
      </div>
    </div>
  );
}

function NotOnTeam() {
  const { user, logout } = useAuth();
  return (
    <div className="grid min-h-screen place-items-center px-4">
      <div className="max-w-sm text-center">
        <div className="mb-6 flex justify-center"><Mark /></div>
        <h1 className="text-xl font-bold">This app is for the AIMVA team</h1>
        <p className="mt-2 text-sm text-muted">{user.email} isn't on the team. If it should be, ask an owner to add it on the Team tab, then sign in again.</p>
        <Button className="mt-6" variant="ghost" onClick={logout}><LogOut className="size-4" /> Sign out</Button>
      </div>
    </div>
  );
}

function Shell() {
  const { user, logout } = useAuth();
  const link = ({ isActive }) => cx("inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm", isActive ? "bg-surface text-strong shadow-[var(--shadow-soft)] font-semibold" : "text-muted hover:text-strong");
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-line bg-bg/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 sm:px-6">
          <Link to="/" aria-label="AIMVA Team home"><Mark /></Link>
          <nav aria-label="Team app" className="flex items-center gap-1">
            <NavLink to="/" end className={link}><ShieldCheck className="size-4" /> Console</NavLink>
            {canSeeQuality(user) && <NavLink to="/quality" className={link}><Gauge className="size-4" /> Quality and usage</NavLink>}
          </nav>
          <div className="ml-auto flex items-center gap-2 text-sm">
            <span className="hidden text-right leading-tight sm:block"><span className="block font-semibold text-strong">{user.name || user.email}</span>
              <span className="text-xs text-faint">{ROLE_LABEL[user.staff_role]}</span></span>
            <Button size="sm" variant="subtle" onClick={logout} aria-label="Sign out"><LogOut className="size-4" /><span className="sm:hidden">Sign out</span></Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        <Suspense fallback={<Loading />}><Outlet /></Suspense>
      </main>
    </div>
  );
}

function RequireTeam({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  if (!user.staff_role) return <NotOnTeam />;
  return children;
}

export default function TeamApp() {
  const { user, loading } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={loading ? <Loading /> : user ? <Navigate to="/" replace /> : <SignIn />} />
      <Route element={<RequireTeam><Shell /></RequireTeam>}>
        <Route index element={<Console />} />
        <Route path="quality" element={canSeeQuality(user) ? <Quality /> : <Navigate to="/" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
