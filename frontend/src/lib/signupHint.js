// A visitor who signs up from a use-case page (/signup?for=clients&industry=healthcare&from=…) starts onboarding
// with those answers already picked. Kept in sessionStorage for this tab only; every read is optional.
const KEY = "aimva_signup_hint";
const FOR = ["own", "personal", "employer"];
const INDUSTRY = ["real_estate", "healthcare", "education", "saas", "retail", "services", "other"];

export function rememberSignupHint(search) {
  try {
    const p = new URLSearchParams(search);
    const hint = { for_whom: FOR.includes(p.get("for")) ? p.get("for") : undefined, industry: INDUSTRY.includes(p.get("industry")) ? p.get("industry") : undefined, from: p.get("from") || undefined };
    if (hint.for_whom || hint.industry || hint.from) sessionStorage.setItem(KEY, JSON.stringify(hint));
  } catch { /* storage blocked */ }
}

export function signupHint() {
  try { return JSON.parse(sessionStorage.getItem(KEY) || "{}") || {}; } catch { return {}; }
}
