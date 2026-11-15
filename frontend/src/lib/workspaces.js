// Workspaces: each project is one (design.md 3.5). The first entry is always the person's own account.
// Opening a project and the "removed from project" guard live in lib/projects.js.
import { useApi } from "./hooks";

export const ROLE_LABEL = { owner: "Owner", admin: "Admin", editor: "Editor", client: "View only" };
export const ROLE_HINT = {
  admin: "Can do everything in this project, including inviting and removing people.",
  editor: "Makes and publishes pages, pictures, videos and campaigns. Replies to and calls leads. No team settings.",
};

export function useWorkspaces() {
  const ws = useApi("/api/workspaces", []);
  const list = Array.isArray(ws.data) ? ws.data : [];
  const active = list.find((w) => w.active) || list[0] || null;
  return { ...ws, list, active, own: list.find((w) => w.own) || list[0] || null };
}

