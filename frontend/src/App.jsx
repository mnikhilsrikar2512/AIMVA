import { lazy, Suspense, useEffect } from "react";
import { toast } from "sonner";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./lib/auth";

// Everything is loaded per route, so the public pages don't download the app (and the app doesn't download them).
const AppLayout = lazy(() => import("./components/AppLayout"));
const Landing = lazy(() => import("./pages/Landing"));
const Tour = lazy(() => import("./pages/marketing/Tour"));
const UseCasesIndex = lazy(() => import("./pages/marketing/UseCases").then((m) => ({ default: m.UseCasesIndex })));
const UseCasePage = lazy(() => import("./pages/marketing/UseCases").then((m) => ({ default: m.UseCasePage })));
const legal = (name) => lazy(() => import("./pages/marketing/Legal").then((m) => ({ default: m[name] })));
const PrivacyPage = legal("PrivacyPage"), TermsPage = legal("TermsPage"), RefundPage = legal("RefundPage"), ContactPage = legal("ContactPage");
const NotFound = lazy(() => import("./pages/marketing/NotFound"));
const auth = (name) => lazy(() => import("./pages/Auth").then((m) => ({ default: m[name] })));
const LoginPage = auth("LoginPage"), SignupPage = auth("SignupPage"), VerifyPage = auth("VerifyPage"), ForgotPage = auth("ForgotPage");
const Dashboard = lazy(() => import("./pages/app/Dashboard"));
const ImageGen = lazy(() => import("./pages/app/ImageGen"));
const VideoGen = lazy(() => import("./pages/app/VideoGen"));
const Websites = lazy(() => import("./pages/app/Websites"));
const Hosting = lazy(() => import("./pages/app/Hosting"));
const Ads = lazy(() => import("./pages/app/Ads"));
const VoiceAgent = lazy(() => import("./pages/app/VoiceAgent"));
const WhatsApp = lazy(() => import("./pages/app/WhatsApp"));
const Leads = lazy(() => import("./pages/app/Leads"));
const Analytics = lazy(() => import("./pages/app/Analytics"));
const Settings = lazy(() => import("./pages/app/Settings"));
const Brand = lazy(() => import("./pages/app/Brand"));
const Command = lazy(() => import("./pages/app/Command"));
const Start = lazy(() => import("./pages/Start"));
const Projects = lazy(() => import("./pages/app/Projects"));

function FullScreenSpinner() {
  return (
    <div className="grid min-h-[50vh] place-items-center" role="status" aria-label="Loading">
      <span className="size-6 animate-spin rounded-full border-2 border-line-strong border-t-strong" />
    </div>
  );
}
const page = (el) => <Suspense fallback={<FullScreenSpinner />}>{el}</Suspense>;

function RequireAuth({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <FullScreenSpinner />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return children;
}

// Agency client access is off (owner decision 2026-11-15), but a view-only membership made before that can still
// exist. It sees Home, Leads, Pages, Results, Analytics and Settings; any other address goes Home instead of loading
// a page whose every call is refused.
const CLIENT_PAGES = new Set(["leads", "websites", "command", "analytics", "settings", "projects"]);

function Away({ text }) {
  useEffect(() => { toast(text, { id: "route-guard" }); }, [text]);
  return <Navigate to="/app" replace />;
}

function Allowed({ path, children }) {
  const { user } = useAuth();
  if (user?.workspace?.role === "client" && !CLIENT_PAGES.has(path.split("/")[0])) return <Away text="You can view this project but not change it." />;
  return children;
}

// Signed in: go where sign-in lands (design.md 3.5): an invite or the app page you were sent away from, else the
// Projects window with two or more projects, else Home. Sign-in sets `landing` on the user it stores.
function GuestOnly({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <FullScreenSpinner />;
  if (!user) return children;
  const from = location.state?.from || "";
  const to = from.startsWith("/invite") || (from.startsWith("/app/") && from !== "/app/") ? from : user.landing === "projects" ? "/app/projects" : "/app";
  return <Navigate to={to} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={page(<Landing />)} />
      <Route path="/tour" element={page(<Tour />)} />
      <Route path="/use-cases" element={page(<UseCasesIndex />)} />
      <Route path="/use-cases/:slug" element={page(<UseCasePage />)} />
      <Route path="/privacy" element={page(<PrivacyPage />)} />
      <Route path="/terms" element={page(<TermsPage />)} />
      <Route path="/refund" element={page(<RefundPage />)} />
      <Route path="/contact" element={page(<ContactPage />)} />
      <Route path="/login" element={<GuestOnly>{page(<LoginPage />)}</GuestOnly>} />
      <Route path="/signup" element={<GuestOnly>{page(<SignupPage />)}</GuestOnly>} />
      <Route path="/verify" element={page(<VerifyPage />)} />
      <Route path="/forgot" element={page(<ForgotPage />)} />
      <Route path="/start" element={<RequireAuth>{page(<Start />)}</RequireAuth>} />
      <Route path="/welcome" element={<Navigate to="/start" replace />} />
      <Route path="/app" element={<RequireAuth>{page(<AppLayout />)}</RequireAuth>}>
        <Route index element={page(<Dashboard />)} />
        {[
          ["brand", Brand], ["images", ImageGen], ["videos", VideoGen], ["websites", Websites], ["hosting", Hosting],
          ["ads/:platform", Ads], ["voice", VoiceAgent], ["whatsapp", WhatsApp], ["leads", Leads],
          ["analytics", Analytics], ["settings", Settings], ["command", Command], ["projects", Projects],
        ].map(([path, C]) => <Route key={path} path={path} element={<Allowed path={path}>{page(<C />)}</Allowed>} />)}
        <Route path="*" element={<Navigate to="/app" replace />} />
      </Route>
      <Route path="*" element={page(<NotFound />)} />
    </Routes>
  );
}
