import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ease } from "../components/Motion";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { Eye, EyeOff, Info, MailCheck } from "lucide-react";
import { toast } from "sonner";
import { Logo } from "../components/Logo";
import { Button, Field, Notice } from "../components/ui";
import { post } from "../lib/api";
import { useAuth } from "../lib/auth";
import { rememberSignupHint } from "../lib/signupHint";

function Shell({ title, subtitle, children, footer }) {
  return (
    <main className="relative grid min-h-dvh place-items-center overflow-hidden bg-bg px-4 py-10">
      <div className="aura pointer-events-none absolute inset-0" aria-hidden />
      <motion.div className="relative w-full max-w-md" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease }}>
        <Logo className="mb-8 justify-center" />
        <motion.div layout className="card p-7 sm:p-9" transition={{ duration: 0.35, ease }}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={title} initial={{ opacity: 0, x: 16 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -16 }} transition={{ duration: 0.25, ease }}>
              <h1 className="text-2xl font-bold text-strong">{title}</h1>
              {subtitle && <p className="mt-1.5 text-sm text-muted">{subtitle}</p>}
              <div className="mt-6">{children}</div>
            </motion.div>
          </AnimatePresence>
        </motion.div>
        {footer && <p className="mt-6 text-center text-sm text-muted">{footer}</p>}
      </motion.div>
    </main>
  );
}

function PasswordInput({ value, onChange, autoComplete = "current-password", placeholder = "••••••••" }) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <input
        className="input pr-10"
        type={show ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoComplete={autoComplete}
        placeholder={placeholder}
        required
      />
      <button
        type="button"
        className="absolute inset-y-0 right-0 grid w-10 place-items-center text-faint hover:text-ink"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? "Hide password" : "Show password"}
      >
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  );
}

function strength(pw) {
  let s = 0;
  if (pw.length >= 8) s++;
  if (pw.length >= 12) s++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) s++;
  if (/\d/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  return Math.min(4, s);
}

function StrengthBar({ pw }) {
  const s = strength(pw);
  const colors = ["bg-rose-500", "bg-rose-500", "bg-amber-400", "bg-lime-400", "bg-emerald-400"];
  if (!pw) return null;
  return (
    <div className="mt-2 flex gap-1">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="h-1 flex-1 overflow-hidden rounded-full bg-ink/[0.06]">
          <motion.div className={`h-full rounded-full ${colors[s]}`} initial={false} animate={{ scaleX: i < s ? 1 : 0 }} style={{ originX: 0 }} transition={{ type: "spring", stiffness: 300, damping: 26 }} />
        </div>
      ))}
    </div>
  );
}

function devNotice(code) {
  if (code) toast.info(`Dev mode (SMTP not set up): your code is ${code}`, { duration: 20000 });
}

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const d = await post("/api/auth/login", { email, password });
      setUser(d.workspace ? { ...d.user, workspace: d.workspace } : d.user);  // a client may land in their workspace
      // Every successful sign-in lands on Home. The one exception is an invite link, which must open to be accepted.
      const from = location.state?.from || "";
      navigate(from.startsWith("/invite") ? from : "/app", { replace: true });
    } catch (err) {
      if (err.status === 403 && err.data?.needs_verification) {
        devNotice(err.data.dev_code);
        navigate(`/verify?email=${encodeURIComponent(email)}`);
        return;
      }
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell
      title="Welcome back"
      subtitle="Sign in to your AIMVA workspace."
      footer={<>New to AIMVA? <Link to="/signup" className="font-semibold text-brand-2 hover:underline">Create an account</Link></>}
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <Notice tone="rose">{error}</Notice>}
        <Field label="Email">
          <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required autoFocus />
        </Field>
        <Field label={<span className="flex justify-between">Password <Link to="/forgot" className="text-brand-2 hover:underline">Forgot?</Link></span>}>
          <PasswordInput value={password} onChange={setPassword} />
        </Field>
        <Button type="submit" busy={busy} className="h-11 w-full">Sign in</Button>
      </form>
    </Shell>
  );
}

export function SignupPage() {
  const [form, setForm] = useState({ name: "", email: "", company: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const { search } = useLocation();
  useEffect(() => { rememberSignupHint(search); }, [search]);  // ?for=…&industry=… from a use-case page
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target ? e.target.value : e }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const d = await post("/api/auth/signup", form);
      devNotice(d.dev_code);
      navigate(`/verify?email=${encodeURIComponent(form.email)}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell
      title="Create your account"
      subtitle="We'll email you a 6-digit code to verify your address."
      footer={<>Already have an account? <Link to="/login" className="font-semibold text-brand-2 hover:underline">Sign in</Link></>}
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <Notice tone="rose">{error}</Notice>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name">
            <input className="input" value={form.name} onChange={set("name")} autoComplete="name" required autoFocus />
          </Field>
          <Field label="Company (optional)">
            <input className="input" value={form.company} onChange={set("company")} autoComplete="organization" />
          </Field>
        </div>
        <Field label="Work email">
          <input className="input" type="email" value={form.email} onChange={set("email")} autoComplete="email" required />
        </Field>
        <Field label="Password" hint="At least 8 characters, mixing letters with numbers or symbols.">
          <PasswordInput value={form.password} onChange={set("password")} autoComplete="new-password" />
          <StrengthBar pw={form.password} />
        </Field>
        <Button type="submit" busy={busy} className="h-11 w-full">Create account</Button>
        <p className="text-center text-xs leading-relaxed text-muted">
          By creating an account you agree to the <Link to="/terms" target="_blank" className="underline underline-offset-2 hover:text-strong">Terms</Link> and
          confirm you've read the <Link to="/privacy" target="_blank" className="underline underline-offset-2 hover:text-strong">Privacy policy</Link>.
        </p>
      </form>
    </Shell>
  );
}

function CodeInput({ value, onChange, onComplete }) {
  const refs = useRef([]);
  const digits = value.padEnd(6, " ").split("").slice(0, 6);
  const setAt = (i, ch) => {
    const arr = value.padEnd(6, " ").split("");
    arr[i] = ch;
    const next = arr.join("").replace(/\s+$/, "");
    onChange(next);
    if (next.replace(/\s/g, "").length === 6) onComplete?.(next);
  };
  return (
    <div className="flex justify-between gap-2" onPaste={(e) => {
      const t = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
      if (t) {
        e.preventDefault();
        onChange(t);
        refs.current[Math.min(t.length, 5)]?.focus();
        if (t.length === 6) onComplete?.(t);
      }
    }}>
      {digits.map((d, i) => (
        <motion.input
          key={i}
          ref={(el) => (refs.current[i] = el)}
          animate={d.trim() ? { scale: [1, 1.08, 1] } : { scale: 1 }}
          transition={{ duration: 0.25 }}
          className={`input h-14 w-full max-w-14 text-center font-display text-2xl font-bold ${d.trim() ? "ring-brand/40" : ""}`}
          inputMode="numeric"
          autoComplete={i === 0 ? "one-time-code" : "off"}
          value={d.trim()}
          aria-label={`Digit ${i + 1}`}
          autoFocus={i === 0}
          onChange={(e) => {
            const typed = e.target.value.replace(/\D/g, "");
            if (typed.length > 2) {
              // Autofill / multi-char insert: spread the digits from this box onward.
              const next = (value.slice(0, i) + typed).slice(0, 6);
              onChange(next);
              refs.current[Math.min(next.length, 5)]?.focus();
              if (next.length === 6) onComplete?.(next);
              return;
            }
            const ch = typed.slice(-1);
            if (!ch) return;
            setAt(i, ch);
            refs.current[i + 1]?.focus();
          }}
          onKeyDown={(e) => {
            if (e.key === "Backspace") {
              e.preventDefault();
              setAt(i, " ");
              if (!d.trim()) refs.current[i - 1]?.focus();
            }
          }}
        />
      ))}
    </div>
  );
}

function useCooldown(initial = 60) {
  const [left, setLeft] = useState(initial);
  useEffect(() => {
    if (left <= 0) return;
    const t = setTimeout(() => setLeft((l) => l - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);
  return [left, setLeft];
}

export function VerifyPage() {
  const [params] = useSearchParams();
  const email = params.get("email") || "";
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [left, setLeft] = useCooldown(60);
  const { setUser } = useAuth();
  const navigate = useNavigate();

  const verify = async (c = code) => {
    if (c.replace(/\s/g, "").length !== 6) return;
    setBusy(true);
    setError("");
    try {
      const d = await post("/api/auth/verify-email", { email, code: c });
      setUser(d.user);
      // A new account goes to the three onboarding questions first, then Home.
      navigate(d.user?.industry ? "/app" : "/welcome", { replace: true });
    } catch (err) {
      setError(err.message);
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    try {
      const d = await post("/api/auth/resend-code", { email });
      devNotice(d.dev_code);
      toast.success("A new code is on its way.");
      setLeft(60);
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <Shell title="Check your inbox" subtitle={<>We sent a 6-digit code to <b className="text-ink">{email}</b>. It expires in 10 minutes.</>}>
      <div className="mb-6 grid place-items-center">
        <div className="grid size-14 place-items-center rounded-2xl bg-emerald-500/10 text-emerald-600">
          <MailCheck className="size-7" />
        </div>
      </div>
      {error && <Notice tone="rose">{error}</Notice>}
      <CodeInput value={code} onChange={setCode} onComplete={verify} />
      <Button className="mt-6 h-11 w-full" busy={busy} onClick={() => verify()}>Verify email</Button>
      <p className="mt-5 text-center text-sm text-muted">
        Didn't get it? Check spam, or{" "}
        {left > 0 ? <span className="text-faint">resend in {left}s</span> : (
          <button className="font-semibold text-brand-2 hover:underline" onClick={resend}>resend code</button>
        )}
      </p>
    </Shell>
  );
}

export function ForgotPage() {
  const [step, setStep] = useState("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const { setUser } = useAuth();
  const navigate = useNavigate();

  const request = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const d = await post("/api/auth/forgot-password", { email });
      devNotice(d.dev_code);
      setStep("reset");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const reset = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const d = await post("/api/auth/reset-password", { email, code, password });
      setUser(d.user);
      toast.success("Password updated.");
      navigate("/app", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell
      title={step === "email" ? "Reset your password" : "Enter code & new password"}
      subtitle={step === "email" ? "We'll email you a reset code." : <>If an account exists for <b className="text-ink">{email}</b>, a code is on its way.</>}
      footer={<Link to="/login" className="font-semibold text-brand-2 hover:underline">Back to sign in</Link>}
    >
      {error && <Notice tone="rose">{error}</Notice>}
      {step === "email" ? (
        <form onSubmit={request} className="space-y-4">
          <Field label="Email">
            <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
          </Field>
          <Button type="submit" busy={busy} className="h-11 w-full">Send reset code</Button>
        </form>
      ) : (
        <form onSubmit={reset} className="space-y-5">
          <CodeInput value={code} onChange={setCode} />
          <Field label="New password">
            <PasswordInput value={password} onChange={setPassword} autoComplete="new-password" />
            <StrengthBar pw={password} />
          </Field>
          <Button type="submit" busy={busy} className="h-11 w-full">Update password</Button>
          <p className="flex items-center gap-1.5 text-xs text-faint"><Info className="size-3.5" /> This signs you out on other devices.</p>
        </form>
      )}
    </Shell>
  );
}
