// What we learned at sign-up (who it's for, website, social presence, agency, budget, team). Saved to the server
// (POST /api/onboarding/answers). Until a server has that endpoint, answers stay in this browser and are sent
// again on the next save, so nothing typed is lost.
import { post } from "./api";

const KEY = "aimva_onboarding_answers";
export const readLocalAnswers = () => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { return {}; } };

export async function saveAnswers(patch) {
  const merged = { ...readLocalAnswers(), ...patch };
  try { localStorage.setItem(KEY, JSON.stringify(merged)); } catch { /* storage blocked */ }
  try { await post("/api/onboarding/answers", { answers: merged }); return true; }
  catch { return false; }  // 404 on older servers: kept locally, resent next time
}

/** Server answers win; local ones fill gaps (e.g. typed before the endpoint existed). */
export const answersFrom = (status) => ({ ...readLocalAnswers(), ...(status?.answers || {}) });
