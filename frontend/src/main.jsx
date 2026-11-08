import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import App from "./App";
import { AuthProvider } from "./lib/auth";
import { TooltipProvider } from "./components/shadcn/tooltip";
import "./index.css";

// Guardrail: a double or triple click on a button counts once. Buttons that should repeat (A+ / A−) opt out with
// data-repeat. Separate deliberate clicks are untouched.
document.addEventListener("click", (e) => {
  if (e.detail < 2) return;
  const b = e.target.closest?.("button, [role=button], a.btn-primary, a.btn-ghost");
  if (b && !b.closest("[data-repeat]")) { e.preventDefault(); e.stopImmediatePropagation(); }
}, true);

// The styles need Safari 16.4+, Chrome 111+ or Firefox 128+ (Tailwind v4). Older browsers get a plain notice
// instead of a silently broken layout.
if (typeof CSS !== "undefined" && !CSS.supports("color", "color-mix(in srgb, red, blue)")) {
  const n = document.createElement("div");
  n.setAttribute("role", "alert");
  n.style.cssText = "position:fixed;inset:auto 0 0 0;z-index:99;padding:12px 16px;background:#1e1913;color:#fff;font:14px/1.4 system-ui,sans-serif;text-align:center";
  n.textContent = "Your browser is out of date, so AIMVA may look broken. Please update Safari, Chrome, Edge or Firefox.";
  document.body.appendChild(n);
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <TooltipProvider>
        <App />
        <Toaster theme="light" position="top-right" richColors closeButton />
        </TooltipProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);

// Installable on phones, and the target for new-lead alerts (public/sw.js). Caches nothing.
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => { navigator.serviceWorker.register("/sw.js").catch(() => {}); });
}
