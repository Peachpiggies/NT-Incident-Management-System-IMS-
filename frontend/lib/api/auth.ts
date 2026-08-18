import { apiClient } from "./client";
import type { LoginRequest, TokenPair } from "../types";

export async function login(payload: LoginRequest): Promise<TokenPair> {
  const { data } = await apiClient.post<TokenPair>("/auth/login", payload);
  return data;
}

export async function logout(refreshToken: string): Promise<void> {
  await apiClient.post("/auth/logout", { refresh_token: refreshToken });
}
