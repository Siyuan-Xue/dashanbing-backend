import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ApiError, authApi } from "../api";
import type { AuthUser, Registration } from "../api";
import { subscribeToSessionExpiry } from "../session";

type AuthContextValue = {
  user: AuthUser | null; checking: boolean; authError: boolean; login: (identity: string, password: string) => Promise<AuthUser>;
  register: (registration: Registration) => Promise<AuthUser>; logout: () => Promise<void>; refresh: () => Promise<AuthUser | null>;
};
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checking, setChecking] = useState(true);
  const [authError, setAuthError] = useState(false);
  const requestGeneration = useRef(0);

  useLayoutEffect(() => subscribeToSessionExpiry(() => {
    requestGeneration.current += 1;
    setUser(null);
    setChecking(false);
    setAuthError(false);
  }), []);

  const refresh = useCallback(async () => {
    const generation = ++requestGeneration.current;
    setChecking(true);
    setAuthError(false);
    try {
      const current = await authApi.me();
      if (generation === requestGeneration.current) {
        setUser(current);
        setAuthError(false);
      }
      return current;
    } catch (error) {
      if (generation === requestGeneration.current) {
        if (error instanceof ApiError && error.status === 401) setUser(null);
        else setAuthError(true);
      }
      return null;
    } finally {
      if (generation === requestGeneration.current) setChecking(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => { requestGeneration.current += 1; };
  }, [refresh]);

  const establishSession = useCallback(async (authenticate: () => Promise<unknown>) => {
    const generation = ++requestGeneration.current;
    setChecking(true);
    setAuthError(false);
    try {
      await authenticate();
      const current = await authApi.me();
      if (generation === requestGeneration.current) {
        setUser(current);
        setChecking(false);
      }
      return current;
    } catch (error) {
      if (generation === requestGeneration.current) setChecking(false);
      throw error;
    }
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user, checking, authError, refresh,
    login: (identity, password) => establishSession(() => authApi.login(identity, password)),
    register: (registration) => establishSession(async () => {
      await authApi.register(registration);
      await authApi.login(registration.username, registration.password);
    }),
    logout: async () => {
      requestGeneration.current += 1;
      await authApi.logout();
      setUser(null);
      setChecking(false);
      setAuthError(false);
    },
  }), [authError, checking, establishSession, refresh, user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
