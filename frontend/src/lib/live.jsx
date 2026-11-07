import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { post } from "./api";
import { useIsClient } from "./auth";

/*
 * Live updates over Server-Sent Events (/api/events). Keeps the unseen-lead badge in sync,
 * shows a toast for new leads, and broadcasts a window "aimva:lead" event so open pages refresh.
 * EventSource reconnects on its own; the server re-sends the current unseen count on reconnect.
 */
const LiveContext = createContext({ unseen: 0, connected: false });
export const useLive = () => useContext(LiveContext);

const SOURCE_LABEL = { website: "landing page", meta: "Meta ads", google: "Google ads", linkedin: "LinkedIn ads",
  whatsapp: "WhatsApp", voice: "voice call", manual: "manual entry" };
const BASE_TITLE = document.title;

// Subscribe a component to live lead events (refresh lists, counts, timelines).
export function useLeadEvents(handler) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    const fn = (e) => ref.current(e.detail);
    window.addEventListener("aimva:lead", fn);
    return () => window.removeEventListener("aimva:lead", fn);
  }, []);
}

// Subscribe to live agent progress ({type: "progress" | "finished", job}).
export function useAgentEvents(handler) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    const fn = (e) => ref.current(e.detail);
    window.addEventListener("aimva:agent", fn);
    return () => window.removeEventListener("aimva:agent", fn);
  }, []);
}

export function LiveProvider({ children }) {
  const [unseen, setUnseen] = useState(0);
  const [connected, setConnected] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const isClient = useIsClient();  // clients view leads; only the team marks them seen
  const viewOnly = useRef(false);
  viewOnly.current = isClient;
  const onLeadsPage = useRef(false);
  onLeadsPage.current = location.pathname === "/app/leads";

  // Visiting the Leads page marks everything as seen.
  useEffect(() => {
    if (location.pathname === "/app/leads" && !isClient) post("/api/leads/seen").then(() => setUnseen(0)).catch(() => {});
  }, [location.pathname, isClient]);

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const es = new EventSource("/api/events", { withCredentials: true });
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.addEventListener("hello", (e) => setUnseen(JSON.parse(e.data).unseen));
    es.addEventListener("seen", () => setUnseen(0));
    es.addEventListener("lead", (e) => {
      const d = JSON.parse(e.data);
      window.dispatchEvent(new CustomEvent("aimva:lead", { detail: d }));
      const name = d.lead.name || d.lead.email || d.lead.phone || "Someone";
      const open = () => navigate(`/app/leads?lead=${d.lead.id}`);
      if (d.type === "created") {
        if (onLeadsPage.current) {
          if (!viewOnly.current) post("/api/leads/seen").catch(() => {});
          setUnseen(0);
        } else {
          setUnseen(d.unseen);
        }
        toast.success(`New lead: ${name}`, {
          description: `From ${SOURCE_LABEL[d.source] || d.source} · score ${d.lead.score}`,
          action: { label: "View", onClick: open },
          duration: 8000,
        });
      } else if (d.source === "whatsapp") {
        toast(`${name} messaged on WhatsApp`, { action: { label: "Open", onClick: open } });
      }
    });
    es.addEventListener("agent", (e) => {
      const d = JSON.parse(e.data);
      window.dispatchEvent(new CustomEvent("aimva:agent", { detail: d }));
      // Big jobs announce themselves wherever you are; small ones only show in the activity feed.
      if (d.type === "finished" && d.job.kind === "launch") {
        (d.job.status === "done" ? toast.success : toast.error)(d.job.title, { action: { label: "Open", onClick: () => navigate("/app") } });
      }
    });
    return () => es.close();
  }, [navigate]);

  // Show the count in the browser tab too, so it's visible from other tabs.
  useEffect(() => {
    document.title = unseen ? `(${unseen}) ${BASE_TITLE}` : BASE_TITLE;
    return () => { document.title = BASE_TITLE; };
  }, [unseen]);

  return <LiveContext.Provider value={{ unseen, connected }}>{children}</LiveContext.Provider>;
}
