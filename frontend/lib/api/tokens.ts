/**
 * Token storage. The backend issues an access+refresh pair (app/schemas/auth.py
 * Token) — there is no session cookie, so both live in memory + localStorage
 * on the client. The access token JWT payload only carries sub/typ/jti/exp
 * (no role/name), which is why AuthProvider always calls GET /users/me after
 * login rather than decoding the token.
 */

const ACCESS_KEY = "ims.access_token";
const REFRESH_KEY = "ims.refresh_token";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string): void {
  window.localStorage.setItem(ACCESS_KEY, access);
  window.localStorage.setItem(REFRESH_KEY, refresh);
  // A lightweight, non-httpOnly marker cookie so middleware.ts can redirect
  // unauthenticated visitors without shipping the real tokens server-side.
  document.cookie = `ims_authed=1; path=/; max-age=${60 * 60 * 24 * 30}; samesite=lax`;
}

export function clearTokens(): void {
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
  document.cookie = "ims_authed=; path=/; max-age=0";
}
