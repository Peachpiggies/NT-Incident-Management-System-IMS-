import { apiClient } from "./client";
import type {
  TicketAssigneeRequest,
  TicketCommentResponse,
  TicketConfirmationRequest,
  TicketCreate,
  TicketDepartmentAssignmentRequest,
  TicketEscalationResponse,
  TicketFilters,
  TicketFunctionalEscalationRequest,
  TicketHistoryResponse,
  TicketPage,
  TicketRejectionRequest,
  TicketResponse,
  TicketTechnicalEscalationRequest,
} from "../types";

export async function listTickets(filters: TicketFilters = {}): Promise<TicketPage> {
  const { data } = await apiClient.get<TicketPage>("/tickets", { params: filters });
  return data;
}

export async function getTicket(id: string): Promise<TicketResponse> {
  const { data } = await apiClient.get<TicketResponse>(`/tickets/${id}`);
  return data;
}

export async function createTicket(payload: TicketCreate): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>("/tickets", payload);
  return data;
}

export async function getTicketComments(id: string): Promise<TicketCommentResponse[]> {
  const { data } = await apiClient.get<TicketCommentResponse[]>(`/tickets/${id}/comments`);
  return data;
}

export async function getTicketHistory(id: string): Promise<TicketHistoryResponse[]> {
  const { data } = await apiClient.get<TicketHistoryResponse[]>(`/tickets/${id}/history`);
  return data;
}

export async function getDashboard(): Promise<Record<string, unknown>> {
  const { data } = await apiClient.get("/tickets/dashboard");
  return data;
}

// ===================== Workflow actions =====================
// One function per POST /tickets/{id}/<action> route in
// app/api/v1/tickets.py. All return the updated TicketResponse except the
// two structured-escalation endpoints, which return the created
// TicketEscalation row (status_code 201).

export async function assignTicket(
  id: string,
  payload: TicketAssigneeRequest
): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(`/tickets/${id}/assign`, payload);
  return data;
}

export async function claimTicket(id: string): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(`/tickets/${id}/claim`);
  return data;
}

export async function assignTicketDepartment(
  id: string,
  payload: TicketDepartmentAssignmentRequest
): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(
    `/tickets/${id}/assign-department`,
    payload
  );
  return data;
}

export async function startTicket(id: string): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(`/tickets/${id}/start`);
  return data;
}

export async function pendingTicket(id: string): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(`/tickets/${id}/pending`);
  return data;
}

/** Generic status-only escalation (flips to ESCALATED, no tier/department bookkeeping). */
export async function escalateTicket(id: string): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(`/tickets/${id}/escalate`);
  return data;
}

/** Structured escalation: re-route to another team, tier unaffected. */
export async function escalateTicketFunctional(
  id: string,
  payload: TicketFunctionalEscalationRequest
): Promise<TicketEscalationResponse> {
  const { data } = await apiClient.post<TicketEscalationResponse>(
    `/tickets/${id}/escalate/functional`,
    payload
  );
  return data;
}

/** Structured escalation: move up the T1 -> T2 -> T3 expertise chain. */
export async function escalateTicketTechnical(
  id: string,
  payload: TicketTechnicalEscalationRequest
): Promise<TicketEscalationResponse> {
  const { data } = await apiClient.post<TicketEscalationResponse>(
    `/tickets/${id}/escalate/technical`,
    payload
  );
  return data;
}

export async function listTicketEscalations(id: string): Promise<TicketEscalationResponse[]> {
  const { data } = await apiClient.get<TicketEscalationResponse[]>(`/tickets/${id}/escalations`);
  return data;
}

export async function receiveEscalatedTicket(id: string): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(`/tickets/${id}/receive_escalated`);
  return data;
}

export async function resolveTicket(id: string): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(`/tickets/${id}/resolve`);
  return data;
}

export async function closeTicket(id: string): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(`/tickets/${id}/close`);
  return data;
}

export async function reopenTicket(id: string): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(`/tickets/${id}/reopen`);
  return data;
}

/** Requester (or a ticket.confirm_any holder) accepts the resolution -> CLOSED. */
export async function confirmTicket(
  id: string,
  payload: TicketConfirmationRequest = {}
): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(`/tickets/${id}/confirm`, payload);
  return data;
}

/** Requester (or a ticket.reject_any holder) rejects the resolution -> back to work. */
export async function rejectTicket(
  id: string,
  payload: TicketRejectionRequest
): Promise<TicketResponse> {
  const { data } = await apiClient.post<TicketResponse>(`/tickets/${id}/reject`, payload);
  return data;
}
