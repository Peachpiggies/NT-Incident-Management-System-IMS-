"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import * as authApi from "@/lib/api/auth";
import * as usersApi from "@/lib/api/users";
import { apiErrorMessage } from "@/lib/api/client";
import { clearTokens, getRefreshToken, setTokens } from "@/lib/api/tokens";
import { primaryRoleCode, type UserResponse } from "@/lib/types";

interface AuthContextValue {
  user: UserResponse | null;
  roleCode: string | null;
  status: "loading" | "authed" | "guest";
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");
  const [error, setError] = useState<string | null>(null);

  const loadProfile = useCallback(async () => {
    try {
      // Access token payload carries only sub/typ/jti/exp — /users/me is the
      // only way to learn who's signed in and what roles they hold.
      const me = await usersApi.getMe();
      setUser(me);
      setStatus("authed");
    } catch {
      clearTokens();
      setUser(null);
      setStatus("guest");
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (getRefreshToken()) {
      void loadProfile();
    } else {
      setStatus("guest");
    }
  }, [loadProfile]);

  const login = useCallback(
    async (email: string, password: string) => {
      setError(null);
      try {
        const tokens = await authApi.login({ email, password });
        setTokens(tokens.access_token, tokens.refresh_token);
        await loadProfile();
        router.push("/dashboard");
      } catch (err) {
        setError(apiErrorMessage(err, "Invalid email or password"));
        throw err;
      }
    },
    [loadProfile, router]
  );

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken();
    try {
      if (refreshToken) await authApi.logout(refreshToken);
    } catch {
      // Best-effort — clear local state regardless of server response.
    }
    clearTokens();
    setUser(null);
    setStatus("guest");
    router.push("/login");
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      roleCode: user ? primaryRoleCode(user) : null,
      status,
      error,
      login,
      logout,
      refreshUser: loadProfile,
    }),
    [user, status, error, login, logout, loadProfile]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
