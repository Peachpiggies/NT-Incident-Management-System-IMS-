import { apiClient } from "./client";
import type {
  CategoryResponse,
  DepartmentSummary,
  PriorityResponse,
  ServiceResponse,
  StatusResponse,
  SubcategoryResponse,
} from "../types";

// These back the New Ticket form's dropdowns and the ticket filter bar.
// GET /priorities and GET /statuses were added alongside this frontend —
// see backend/app/api/v1/references.py.

export async function listPriorities(): Promise<PriorityResponse[]> {
  const { data } = await apiClient.get<PriorityResponse[]>("/priorities");
  return data;
}

export async function listStatuses(): Promise<StatusResponse[]> {
  const { data } = await apiClient.get<StatusResponse[]>("/statuses");
  return data;
}

export async function listCategories(): Promise<CategoryResponse[]> {
  const { data } = await apiClient.get<CategoryResponse[]>("/categories");
  return data;
}

export async function listSubcategories(categoryId?: string): Promise<SubcategoryResponse[]> {
  const { data } = await apiClient.get<SubcategoryResponse[]>("/subcategories", {
    params: categoryId ? { category_id: categoryId } : undefined,
  });
  return data;
}

export async function listServices(subcategoryId?: string): Promise<ServiceResponse[]> {
  const { data } = await apiClient.get<ServiceResponse[]>("/services", {
    params: subcategoryId ? { subcategory_id: subcategoryId } : undefined,
  });
  return data;
}

export async function listDepartments(): Promise<DepartmentSummary[]> {
  const { data } = await apiClient.get<DepartmentSummary[]>("/departments");
  return data;
}
