import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, setUnauthorizedHandler, tokenStore } from "../api/client";
import type { User } from "../api/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [token, setToken] = useState(tokenStore.get);
  const me = useQuery({
    queryKey: ["me", token],
    queryFn: api.me,
    enabled: token !== null,
    retry: false,
  });

  const logout = useCallback(() => {
    tokenStore.clear();
    setToken(null);
    qc.clear();
  }, [qc]);

  useEffect(() => setUnauthorizedHandler(logout), [logout]);

  const login = useCallback(
    async (email: string, password: string) => {
      const { access_token } = await api.login(email, password);
      tokenStore.set(access_token);
      await qc.fetchQuery({ queryKey: ["me", access_token], queryFn: api.me });
      setToken(access_token);
    },
    [qc],
  );

  const value = useMemo<AuthState>(
    () => ({
      user: token ? (me.data ?? null) : null,
      loading: token !== null && me.isPending,
      login,
      logout,
    }),
    [token, me.data, me.isPending, login, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
