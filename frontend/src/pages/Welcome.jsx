// Right after a successful sign-up, on its own calm page (never a pop-up), once. One question per screen, and each
// answer changes what AIMVA does next (design.md 4.1). Every question can be skipped; Back keeps what was typed.
import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { toast } from "sonner";
import { Logo } from "../components/Logo";
import { BrandBasicsForm, ProfileForm } from "../components/Onboarding";
import { Button, Field, ListSkeleton, cx } from "../components/ui";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/hooks";
import { answersFrom, saveAnswers } from "../lib/onboardingAnswers";
import { signupHint } from "../lib/signupHint";

const FOR_WHOM = [
  ["own", "My company", "A business I own or run."],
  ["personal", "Just me", "My own name or personal brand: a creator, coach, consultant or freelancer."],
  ["clients", "My clients", "I'm an agency or freelancer running marketing for other businesses."],
  ["employer", "The company I work for", "I handle marketing as part of a team."],
];
const PRESENCE = [["instagram", "Instagram"], ["facebook", "Facebook"], ["google_business", "Google Business"], ["linkedin", "LinkedIn"],
  ["whatsapp", "WhatsApp Business"], ["youtube", "YouTube"]];
const ACQUISITION = [
  ["agency", "An ad agency runs our ads", "AIMVA can work alongside them: it tracks every lead their ads bring and calls them back in a minute."],
  ["ads_self", "We run ads ourselves", "You'll get ad drafts, sizes for every placement and a check before anything goes live."],
  ["word_of_mouth", "Word of mouth and referrals", "We'll start with a page and WhatsApp, so referrals have somewhere to land."],
  ["none", "We're just getting started", "We'll start small: one page, one lead form, no spend needed."],
];
const BUDGET = [["none", "Nothing yet"], ["lt25k", "Under ₹25,000"], ["25k_1l", "₹25,000 – ₹1 lakh"], ["gt1l", "Over ₹1 lakh"]];
const TEAM = [["solo", "Just me"], ["small", "2 to 10 people"], ["large", "More than 10"]];

function Choice({ on, title, text, onClick, multi }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={on}
      className={cx("flex w-full items-start gap-3 rounded-xl px-4 py-3 text-left ring-1 transition",
        on ? "bg-surface ring-strong" : "ring-line-strong hover:bg-surface hover:ring-strong/30")}>
      <span className={cx("mt-0.5 grid size-5 shrink-0 place-items-center border transition", multi ? "rounded-md" : "rounded-full",
        on ? "border-strong bg-strong text-white" : "border-line-strong")}>{on && <Check className="size-3" strokeWidth={3} />}</span>
      <span className="min-w-0">
        <span className="block text-[15px] font-medium text-strong">{title}</span>
        {text && <span className="mt-0.5 block text-sm text-muted">{text}</span>}
      </span>
    </button>
  );
}

const normUrl = (u) => { const s = u.trim(); if (!s) return ""; return /^https?:\/\//i.test(s) ? s : `https://${s}`; };

export default function Welcome() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data: status, error } = useApi("/api/onboarding");
  const alreadyDone = useRef(!!user?.industry);  // decided on arrival: someone who already answered goes to Home
  // Signed up from a use-case page? Start with that answer picked (they can still change it).
  const [a, setA] = useState(() => ({ ...answersFrom(null), ...(signupHint().for_whom && { for_whom: signupHint().for_whom }) }));
  const [i, setI] = useState(0);
  useEffect(() => { if (status) setA((x) => ({ ...answersFrom(status), ...x })); }, [status]);
  useEffect(() => { document.title = "Welcome · AIMVA"; return () => { document.title = "AIMVA"; }; }, []);

  const set = (patch) => setA((x) => ({ ...x, ...patch }));
  const personal = a.for_whom === "personal";
  const clients = a.for_whom === "clients";

  // The questions, in order. Each one only shows if it still matters given the earlier answers.
  const steps = useMemo(() => [
    { key: "for_whom", title: "Who are you setting AIMVA up for?", text: "This decides how your workspace is arranged.", ready: !!a.for_whom },
    { key: "business", title: clients ? "First, your own agency." : personal ? "Tell us about you." : "Tell us about the business.",
      text: clients ? "You'll add each client as their own workspace after this." : "We use this to write your first page, your call assistant's script and your ad copy." , custom: true },
    { key: "website", title: personal ? "Do you have a website or a link in bio?" : "Do you already have a website?",
      text: "If you do, AIMVA reads it to write your page and ads, so you don't retype anything.", ready: a.has_website === false || (a.has_website && !!a.website?.trim()) },
    { key: "presence", title: "Where are you online already?", text: "Pick all that apply. We'll suggest connecting these first and match their look.", ready: true },
    { key: "acquisition", title: "How do customers find you today?", text: null, ready: !!a.acquisition },
    ...(a.acquisition && a.acquisition !== "none" ? [{ key: "budget", title: "Roughly what goes into ads each month?", text: "Only used to suggest budgets. It's never spent without you.", ready: !!a.monthly_budget }] : []),
    ...(!personal ? [{ key: "team", title: "Who else will use AIMVA?", text: "Working alone is fine. You can invite people any time.", ready: !!a.team_size }] : []),
    { key: "brand", title: "Last one: how your brand looks and sounds.", text: "Every picture, page and ad will use these colours and this voice. Change it any time in Settings → Brand kit.", custom: true },
  ], [a, clients, personal]);

  if (alreadyDone.current || error) return <Navigate to="/app" replace />;
  const step = steps[Math.min(i, steps.length - 1)];
  const last = i >= steps.length - 1;

  const finish = () => {
    navigate("/app", { replace: true });
    if (clients) setTimeout(() => toast("Add your first client when you're ready.", { action: { label: "Add a client", onClick: () => window.dispatchEvent(new CustomEvent("aimva:palette")) }, duration: 9000 }), 600);
    else if (a.team_size && a.team_size !== "solo") setTimeout(() => toast("Invite your team when you're ready.", { action: { label: "Invite", onClick: () => navigate("/app/settings?tab=team") }, duration: 9000 }), 600);
  };
  const next = async (patch = {}) => {
    const merged = { ...a, ...patch };
    setA(merged);
    const { for_whom, has_website, website, presence, handles, acquisition, agency_name, monthly_budget, team_size } = merged;
    saveAnswers({ for_whom, has_website, website: website ? normUrl(website) : "", presence, handles, acquisition, agency_name, monthly_budget, team_size });
    if (last) finish(); else setI((n) => n + 1);
  };
  const skip = () => (last ? finish() : setI((n) => n + 1));
  const presence = a.presence || [];
  const togglePresence = (k) => set({ presence: presence.includes(k) ? presence.filter((x) => x !== k) : [...presence.filter((x) => x !== "none"), k] });

  return (
    <div className="min-h-dvh bg-bg">
      <div className="aura pointer-events-none fixed inset-x-0 top-0 h-[360px] opacity-40" aria-hidden />
      <header className="relative mx-auto flex max-w-2xl items-center justify-between px-6 py-6">
        <Logo />
        <button type="button" className="btn-subtle btn-sm" onClick={finish}>Skip setup</button>
      </header>
      <main className="relative mx-auto max-w-2xl px-6 pb-16 pt-2 sm:pt-8">
        <div className="flex items-center gap-3 text-sm text-muted">
          {i > 0 && <button type="button" onClick={() => setI((n) => n - 1)} className="btn-subtle btn-sm -ml-3 px-2" aria-label="Back"><ArrowLeft className="size-4" /></button>}
          <span className="tabular-nums">{i + 1} of {steps.length}</span>
          <span className="h-1 w-32 overflow-hidden rounded-full bg-line-strong/50" aria-hidden><span className="block h-full bg-strong transition-[width] duration-500" style={{ width: `${((i + 1) / steps.length) * 100}%` }} /></span>
        </div>
        <h1 className="serif-moment mt-4 text-[34px] leading-tight text-strong sm:text-4xl">
          {i === 0 ? <>Welcome, <em className="text-warm">{user?.name?.split(" ")[0]}</em>. </> : null}{step.title}
        </h1>
        {step.text && <p className="mt-3 max-w-lg text-[15px] text-muted">{step.text}</p>}

        <div key={step.key} className="mt-8 max-w-xl animate-[rise_.35s_cubic-bezier(.22,1,.36,1)]">
          {step.key === "for_whom" && (
            <div className="space-y-2">{FOR_WHOM.map(([k, t, d]) => <Choice key={k} on={a.for_whom === k} title={t} text={d} onClick={() => next({ for_whom: k })} />)}</div>
          )}

          {step.key === "business" && (!status ? <ListSkeleton rows={3} /> : (
            <ProfileForm status={status} intro={null} submitLabel="Continue" autoFocus
              nameLabel={personal ? "Your name or brand name" : clients ? "Agency name" : "Business name"}
              namePlaceholder={personal ? "Dr. Meera Rao" : clients ? "Northstar Media" : "Skyline Homes"}
              onSaved={() => next()} secondary={<button type="button" className="btn-subtle" onClick={skip}>Skip</button>} />
          ))}

          {step.key === "website" && (
            <div className="space-y-4">
              <div className="space-y-2">
                <Choice on={a.has_website === true} title="Yes" onClick={() => set({ has_website: true })} />
                {a.has_website === true && (
                  <div className="pl-8"><input className="input" autoFocus inputMode="url" placeholder="skylinehomes.in" value={a.website || ""} onChange={(e) => set({ website: e.target.value })} aria-label="Website address" maxLength={300} /></div>
                )}
                <Choice on={a.has_website === false} title="Not yet" text="No problem. Your first AIMVA page will be your website." onClick={() => next({ has_website: false, website: "" })} />
              </div>
            </div>
          )}

          {step.key === "presence" && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-1.5">
                {PRESENCE.map(([k, l]) => <button key={k} type="button" aria-pressed={presence.includes(k)} onClick={() => togglePresence(k)}
                  className={cx("h-9 rounded-full px-3.5 text-sm transition", presence.includes(k) ? "bg-strong text-white" : "bg-surface-2 text-ink hover:bg-line-strong/40")}>{l}</button>)}
                <button type="button" aria-pressed={presence.includes("none")} onClick={() => set({ presence: presence.includes("none") ? [] : ["none"] })}
                  className={cx("h-9 rounded-full px-3.5 text-sm transition", presence.includes("none") ? "bg-strong text-white" : "text-muted hover:bg-surface-2")}>None yet</button>
              </div>
              {presence.some((k) => ["instagram", "facebook", "linkedin", "youtube"].includes(k)) && (
                <div className="grid gap-3 sm:grid-cols-2">
                  {presence.filter((k) => ["instagram", "facebook", "linkedin", "youtube"].includes(k)).map((k) => (
                    <Field key={k} label={`${PRESENCE.find((p) => p[0] === k)[1]} handle or link (optional)`}>
                      <input className="input" value={a.handles?.[k] || ""} maxLength={200} placeholder={k === "instagram" ? "@skylinehomes" : "link or name"}
                        onChange={(e) => set({ handles: { ...(a.handles || {}), [k]: e.target.value } })} />
                    </Field>
                  ))}
                </div>
              )}
            </div>
          )}

          {step.key === "acquisition" && (
            <div className="space-y-2">
              {ACQUISITION.map(([k, t, d]) => (
                <div key={k}>
                  <Choice on={a.acquisition === k} title={t} text={a.acquisition === k ? d : null} onClick={() => (k === "agency" ? set({ acquisition: k }) : next({ acquisition: k }))} />
                  {k === "agency" && a.acquisition === "agency" && (
                    <div className="mt-2 pl-8"><input className="input" autoFocus placeholder="Agency name (optional)" value={a.agency_name || ""} maxLength={160} onChange={(e) => set({ agency_name: e.target.value })} /></div>
                  )}
                </div>
              ))}
            </div>
          )}

          {step.key === "budget" && (
            <div className="space-y-2">{BUDGET.map(([k, l]) => <Choice key={k} on={a.monthly_budget === k} title={l} onClick={() => next({ monthly_budget: k })} />)}</div>
          )}

          {step.key === "team" && (
            <div className="space-y-2">{TEAM.map(([k, l]) => <Choice key={k} on={a.team_size === k} title={l} text={a.team_size === k && k !== "solo" ? "You can invite them from Settings → Team, and choose what each person can do." : null} onClick={() => next({ team_size: k })} />)}</div>
          )}

          {step.key === "brand" && <BrandBasicsForm company={user?.company} onSaved={finish} onSkip={finish} />}

          {!step.custom && (
            <div className="mt-8 flex items-center gap-3">
              <Button onClick={() => next()} disabled={!step.ready}>Continue <ArrowRight className="size-4" /></Button>
              <button type="button" className="btn-subtle" onClick={skip}>Skip this question</button>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
