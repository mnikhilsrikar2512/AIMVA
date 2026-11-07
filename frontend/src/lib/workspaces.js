// Workspaces (own account + agency clients). The first entry is always the person's own account.
import { useEffect } from "react";
import { toast } from "sonner";
import { get, post } from "./api";
import { useApi } from "./hooks";

export const ROLE_LABEL = { owner: "Owner", admin: "Admin", editor: "Editor", client: "Client" };
export const ROLE_HINT = {
  admin: "Everything, including team and billing.",
  editor: "Makes and publishes pages, pictures and campaigns. Calls leads. No team or billing.",
  client: "Sees their leads, pages and results. Approves or asks for changes. Can't edit.",
};

export function useWorkspaces() {
  const ws = useApi("/api/workspaces", []);
  const list = Array.isArray(ws.data) ? ws.data : [];
  const active = list.find((w) => w.active) || list[0] || null;
  return { ...ws, list, active, own: list.find((w) => w.own) || list[0] || null };
}

/** Switch and reload, so every list in the app is scoped to the new workspace. */
export async function switchWorkspace(id, name) {
  await post(`/api/workspaces/${id}/switch`);
  try { sessionStorage.setItem("aimva_switched_to", name || ""); } catch { /* storage blocked */ }
  window.location.assign("/app");
}

/** After a reload from a switch, say where you are now. Listens for "removed from workspace" too. */
export function useWorkspaceGuards() {
  useEffect(() => {
    let name = null;
    try { name = sessionStorage.getItem("aimva_switched_to"); sessionStorage.removeItem("aimva_switched_to"); } catch { /* storage blocked */ }
    if (name) toast(`Now working in ${name}`);
    const lost = async () => {
      try {
        const list = await get("/api/workspaces");
        const own = list.find((w) => w.own) || list[0];
        if (own && !own.active) {
          await post(`/api/workspaces/${own.id}/switch`);
          try { sessionStorage.setItem("aimva_switched_to", "your own account (you no longer have access to that client)"); } catch { /* storage blocked */ }
          window.location.assign("/app");
        }
      } catch { /* leave it; the page shows its own error */ }
    };
    window.addEventListener("aimva:workspace-lost", lost);
    return () => window.removeEventListener("aimva:workspace-lost", lost);
  }, []);
}
