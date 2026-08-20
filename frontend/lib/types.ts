/**
 * Types mirrored from the backend Pydantic schemas (app/schemas/**).
 * Keep field names/shapes in exact sync with the Python source — do not
 * "clean up" naming here, since that's what makes this trustworthy.
 */

// ===================== Auth (app/schemas/auth.py) =====================

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
}

export interface LoginRequest {
  email: string;
  password: string;
}

// ===================== References (app/schemas/references/*) =====================

export interface RoleSummary {
  id: string;
  code: string; // customer | helpdesk_t1 | helpdesk_t2 | manager | admin
  name: string;
}

export interface DepartmentSummary {
  id: string;
  name: string;
}

export interface CategorySummary {
  id: string;
  code: string;
  name: string;
  color: string | null;
  icon: string | null;
}

export interface PrioritySummary {
  id: string;
  name: string;
  sort_order: number;
  color: string | null;
}

export interface StatusSummary {
  id: string;
  name: string;
  color: string | null;
  is_closed: boolean;
}

// Full reference records, from the new GET /priorities and /statuses routes.
export interface PriorityResponse {
  id: string;
  code: string;
  name: string;
  color: string | null;
  sla_minutes: number | null;
  sort_order: number;
  is_active: boolean;
  created_at: string;
}

export interface StatusResponse {
  id: string;
  code: string;
  name: string;
  color: string | null;
  is_closed: boolean;
  sort_order: number;
  is_active: boolean;
  created_at: string;
}

export interface CategoryResponse {
  id: string;
  code: string;
  name: string;
  color: string | null;
  icon: string | null;
  sort_order: number;
  is_active: boolean;
  created_at: string;
}

export interface SubcategoryResponse {
  id: string;
  category_id: string;
  code: string;
  name: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
}

export interface ServiceResponse {
  id: string;
  subcategory_id: string;
  code: string;
  name: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
}

// ===================== Users (app/schemas/references/user.py) =====================
// NOTE: no `full_name` column and no single `role` — roles are plural (M2M).

export interface UserResponse {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  employee_code: string | null;
  phone: string | null;
  department: DepartmentSummary | null;
  roles: RoleSummary[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export function fullName(user: Pick<UserResponse, "first_name" | "last_name">): string {
  const last = user.last_name === "-" ? "" : user.last_name;
  return [user.first_name, last].filter(Boolean).join(" ");
}

export function primaryRoleCode(user: UserResponse): string | null {
  // Highest-privilege role wins for UI purposes (nav, escalation rail).
  const order = ["admin", "manager", "helpdesk_t2", "helpdesk_t1", "customer"];
  const codes = user.roles.map((r) => r.code);
  return order.find((code) => codes.includes(code)) ?? codes[0] ?? null;
}

// ===================== Users (shared summary, app/schemas/common.py) =====================

export interface UserSummary {
  id: string;
  full_name: string;
  email: string;
}

// ===================== Tickets (app/schemas/ticket.py) =====================

export type TicketSource = "WEB" | "EMAIL" | "PHONE" | "CHAT" | "API";

export interface TicketCreate {
  title: string;
  description: string;
  category_id: string;
  subcategory_id?: string | null;
  service_id?: string | null;
  priority_id: string;
  department_id?: string | null;
  source?: TicketSource;
}

export interface TicketSummary {
  id: string;
  ticket_no: string;
  title: string;
  status: StatusSummary;
  priority: PrioritySummary;
  requester: UserSummary;
  assignee: UserSummary | null;
  created_at: string;
  // Present on the actual API response (list endpoints return the same
  // TicketResponse shape as ticket detail) even though this summary type
  // only declares a subset of fields.
  escalation_locked_department_id?: string | null;
  escalation_locked_department?: DepartmentSummary | null;
}

export interface TicketResponse {
  id: string;
  ticket_no: string;
  title: string;
  description: string;
  requester: UserSummary;
  requester_id: string;
  assignee: UserSummary | null;
  assigned_to: string | null;
  department: DepartmentSummary | null;
  department_id: string | null;
  category: CategorySummary;
  category_id: string;
  priority: PrioritySummary;
  priority_id: string;
  status: StatusSummary;
  status_id: string;
  current_tier: number;
  // Set while a tier/department has escalated this ticket away and hasn't
  // been overridden by a manual reassignment yet (see backend
  // TicketEscalationService / AssignmentService.claim & assign_user).
  escalation_locked_department: DepartmentSummary | null;
  escalation_locked_department_id: string | null;
  escalation_locked_tier: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface TicketPage {
  items: TicketSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface TicketFilters {
  q?: string;
  status_id?: string;
  category_id?: string;
  priority_id?: string;
  department_id?: string;
  assignee_id?: string;
  requester_id?: string;
  limit?: number;
  offset?: number;
  sort_by?: "created_at" | "updated_at" | "ticket_no" | "due_at";
  sort_order?: "asc" | "desc";
}

export interface TicketCommentResponse {
  id: string;
  ticket_id: string;
  author: UserSummary;
  body: string;
  is_internal: boolean;
  created_at: string;
}

export interface TicketHistoryResponse {
  id: string;
  ticket_id: string;
  field: string;
  old_value: string | null;
  new_value: string | null;
  changed_by: string | null;
  changed_at: string;
}

// ===================== Ticket workflow actions (app/api/v1/tickets.py) =====================
// Request bodies and the one non-Ticket response shape (escalation) used by
// the assign/claim/escalate/resolve/etc. action endpoints.

export interface TicketAssigneeRequest {
  assignee_id?: string | null;
  reason?: string | null;
}

export interface TicketDepartmentAssignmentRequest {
  department_id: string;
  reason?: string | null;
}

export interface TicketFunctionalEscalationRequest {
  to_department_id: string;
  reason_code?: string | null;
  comment?: string | null;
}

export type TicketTechnicalReasonCode =
  | "SKILL_REQUIRED"
  | "COMPLEXITY"
  | "ACCESS_REQUIRED"
  | "SYSTEM_DEPENDENCY"
  | "UNRESOLVED_AFTER_ATTEMPTS"
  | "SLA_RISK"
  | "MDDR_RISK";

export interface TicketTechnicalEscalationRequest {
  to_tier: number;
  reason_code: TicketTechnicalReasonCode;
  to_department_id?: string | null;
  comment?: string | null;
  allow_tier_skip?: boolean;
}

export interface TicketEscalationResponse {
  id: string;
  ticket_id: string;
  escalation_type: string;
  from_tier: number;
  to_tier: number;
  from_department_id: string | null;
  to_department_id: string | null;
  from_user_id: string | null;
  reason_code: string | null;
  comment: string | null;
  escalated_by: string | null;
  escalated_at: string;
}

export interface TicketConfirmationRequest {
  feedback?: string | null;
}

export interface TicketRejectionRequest {
  reason: string;
}

// ===================== Dashboard (app/schemas/dashboard.py) =====================

export type DashboardScope = "executive" | "manager" | "helpdesk" | "customer";

export interface DashboardSummaryResponse {
  total_tickets: number;
  open_tickets: number;
  unassigned_tickets: number;
  resolved_tickets: number;
  closed_tickets: number;
  sla_breached_tickets: number;
  active_users: number | null;
}

export interface AnalyticsMetricResponse {
  from_date: string | null;
  to_date: string | null;
  mddr_minutes: number | null;
  mtta_minutes: number | null;
  mttr_minutes: number | null;
  mddr_sample_size: number;
  mtta_sample_size: number;
  mttr_sample_size: number;
}

export interface TrendPoint {
  date: string;
  value: number;
}

export interface DistributionItem {
  label: string;
  value: number;
  percentage: number | null;
}

export interface RecentActivityItem {
  id: string;
  actor_name: string;
  action: string;
  target: string | null;
  created_at: string;
}

export interface DashboardOverviewResponse {
  scope: DashboardScope;
  period_start: string | null;
  period_end: string | null;
  summary: DashboardSummaryResponse;
  metrics: AnalyticsMetricResponse;
  tickets_by_status: DistributionItem[];
  tickets_by_priority: DistributionItem[];
  tickets_by_department: DistributionItem[];
  sla_summary: Record<string, number>;
  ticket_trend: TrendPoint[];
  mddr_trend: TrendPoint[];
  recent_activity: RecentActivityItem[];
  change_summary: Record<string, number>;
}

// ===================== API envelope =====================

export interface ApiError {
  detail: string | { msg: string; loc: (string | number)[] }[];
}
