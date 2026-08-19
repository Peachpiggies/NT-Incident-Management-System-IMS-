import { apiClient } from "./client";
import type { DashboardOverviewResponse, DashboardScope } from "../types";

// Maps a signed-in user's primary role to the dashboard scope that role is
// permitted to view (see AnalyticsService.overview's role checks on the
// backend: executive/manager scopes require admin|manager, helpdesk scope
// requires admin|manager|helpdesk_t1|helpdesk_t2, customer is self-serve).
export function scopeForRole(roleCode: string | null): DashboardScope {
  switch (roleCode) {
    case "admin":
    case "manager":
      return "manager";
    case "helpdesk_t1":
    case "helpdesk_t2":
      return "helpdesk";
    default:
      return "customer";
  }
}

export async function getDashboardOverview(
  scope: DashboardScope,
  params: { from_date?: string; to_date?: string } = {}
): Promise<DashboardOverviewResponse> {
  const { data } = await apiClient.get<DashboardOverviewResponse>(`/dashboards/${scope}`, { params });
  return data;
}
