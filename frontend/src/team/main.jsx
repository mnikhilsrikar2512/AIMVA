import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Toaster } from "sonner";
import TeamApp from "./TeamApp";
import { AuthProvider } from "../lib/auth";
import { TooltipProvider } from "../components/shadcn/tooltip";
import "./team.css";

// Same double-click guard as the customer app: a double click on a button counts once.
document.addEventListener("click", (e) => {
  if (e.detail < 2) return;
  const b = e.target.closest?.("button, [role=button], a.btn-primary, a.btn-ghost");
  if (b && !b.closest("[data-repeat]")) { e.preventDefault(); e.stopImmediatePropagation(); }
}, true);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <TooltipProvider>
          <TeamApp />
          <Toaster theme="light" position="top-right" richColors closeButton />
        </TooltipProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
