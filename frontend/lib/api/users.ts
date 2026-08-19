import { apiClient } from "./client";
import type { UserResponse } from "../types";

export async function getMe(): Promise<UserResponse> {
  const { data } = await apiClient.get<UserResponse>("/users/me");
  return data;
}

export async function listUsers(): Promise<UserResponse[]> {
  // Requires user.manage; only call this from admin-gated UI.
  const { data } = await apiClient.get<UserResponse[]>("/users");
  return data;
}
