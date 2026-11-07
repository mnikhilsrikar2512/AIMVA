import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { get, post } from "./api";

const AuthContext = createContext(null);

// /api/auth/me returns the person and, separately, the client workspace they're working in. Keep both on `user`
// (workspace is null in their own account) so client-role checks and per-workspace defaults work.
const withWorkspace = (d) => ({ ...d.user, workspace: d.workspace || null });

export function AuthProvider({ children }) {
  const [user, setUserState] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    get("/api/auth/me")
      .then((d) => setUserState(withWorkspace(d)))
      .catch(() => setUserState(null))
      .finally(() => setLoading(false));
  }, []);

  // Sign-in replies carry only the person: look up the workspace they land in.
  const setUser = useCallback((u) => {
    setUserState(u);
    if (u && !("workspace" in u)) {
      get("/api/auth/me").then((d) => setUserState((cur) => (cur && cur.id === d.user.id ? { ...cur, workspace: d.workspace || null } : cur))).catch(() => {});
    }
  }, []);

  const logout = useCallback(async () => {
    await post("/api/auth/logout").catch(() => {});
    setUserState(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, setUser, loading, logout }}>{children}</AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
