import { apiClient } from "./client";
import type {
  TicketCommentResponse,
  TicketCreate,
  TicketFilters,
  TicketHistoryResponse,
  TicketPage,
  TicketResponse,
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
