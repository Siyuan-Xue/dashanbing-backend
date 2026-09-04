import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { authApi, AuthUser, Registration } from "../api";

type AuthContextValue = {
  user: AuthUser | null; checking: boolean; login: (identity: string, password: string) => Promise<AuthUser>;
  register: (registration: Registration) => Promise<AuthUser>; logout: () => Promise<void>; refresh: () => Promise<AuthUser | null>;
};
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checking, setChecking] = useState(true);
  const refresh = useCallback(async () => {
    try { const current = await authApi.me(); setUser(current); return current; }
    catch { setUser(null); return null; }
    finally { setChecking(false); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const value = useMemo<AuthContextValue>(() => ({
    user, checking, refresh,
    login: async (identity, password) => { await authApi.login(identity, password); const current = await authApi.me(); setUser(current); return current; },
    register: async (registration) => { await authApi.register(registration); await authApi.login(registration.username, registration.password); const current = await authApi.me(); setUser(current); return current; },
    logout: async () => { await authApi.logout(); setUser(null); },
  }), [checking, refresh, user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
