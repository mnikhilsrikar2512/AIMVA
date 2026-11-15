// Projects (design.md 3.5): every business or idea the person runs. Each project is a workspace underneath, so
// opening one is the same switch as before, and every list in the app is scoped to it after a reload.
import { useEffect } from "react";
import { toast } from "sonner";
import { get, post } from "./api";
import { useApi } from "./hooks";

/** Module keys used by /api/start, /api/projects/{id}/modules and /api/route, and where each one lives. */
export const MODULE_ROUTES = {
  page: "/app/websites", whatsapp: "/app/whatsapp", calls: "/app/voice", pictures: "/app/images",
  campaigns: "/app/ads/meta", videos: "/app/videos", leads: "/app/leads", results: "/app/command",
};
export const MODULE_LABEL = {
  page: "Page", whatsapp: "WhatsApp replies", calls: "Calls", pictures: "Pictures", campaigns: "Campaigns", videos: "Videos",
};

/** Open projects (archived ones are asked for separately). Newest activity first, as the server sends them. */
export function useProjects(archived = false) {
  const res = useApi(archived ? "/api/projects?archived=true" : "/api/projects", []);
  const list = Array.isArray(res.data) ? res.data : [];
  return { ...res, list, active: list.find((p) => p.active) || null };
}

/** Where a module's prompt lands: the module's page with the sentence ready in its prompt. */
export const moduleHref = (key, prompt) => {
  const to = MODULE_ROUTES[key] || "/app";
  return prompt ? `${to}${to.includes("?") ? "&" : "?"}prompt=${encodeURIComponent(prompt)}` : to;
};

/** Open a project and reload, so nothing from the previous project stays on screen. */
export async function openProject(p, to = "/app") {
  await post(`/api/workspaces/${p.id}/switch`);
  try { sessionStorage.setItem("aimva_switched_to", p.name || ""); } catch { /* storage blocked */ }
  window.location.assign(to);
}

/** After a reload from opening a project, say where you are. Also handles "you were removed from that project". */
export function useProjectGuards() {
  useEffect(() => {
    let name = null;
    try { name = sessionStorage.getItem("aimva_switched_to"); sessionStorage.removeItem("aimva_switched_to"); } catch { /* storage blocked */ }
    if (name) toast(`Now in ${name}`, { id: "project-open" });
    const lost = async () => {
      try {
        const list = await get("/api/projects");
        const own = list.find((p) => p.own) || list[0];
        if (own && !own.active) {
          await post(`/api/workspaces/${own.id}/switch`);
          try { sessionStorage.setItem("aimva_switched_to", `${own.name} (you no longer have access to the other project)`); } catch { /* storage blocked */ }
          window.location.assign("/app/projects");
        }
      } catch { /* leave it; the page shows its own error */ }
    };
    window.addEventListener("aimva:workspace-lost", lost);
    return () => window.removeEventListener("aimva:workspace-lost", lost);
  }, []);
}
