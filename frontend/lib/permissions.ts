/**
 * Mirrors ROLE_PERMISSION_CODES in backend/app/seed.py so the UI only
 * offers actions a role can actually perform. This is a UI convenience
 * only, not a security boundary -- the backend's `require_permission()`
 * dependency (checked against the live `role_permissions` table) is the
 * real enforcement point. Keep this in sync with seed.py by hand; there
 * is no shared source of truth between the two languages.
 */

export type RoleCode = "customer" | "helpdesk_t1" | "helpdesk_t2" | "manager" | "admin";

const ROLE_PERMISSION_CODES: Record<Exclude<RoleCode, "admin">, ReadonlySet<string>> = {
  customer: new Set([
    "dashboard.view",
    "ticket.create",
    "ticket.read_own",
    "ticket.comment",
    "ticket.attachment_add",
    "ticket.update",
    "ticket.confirm",
    "ticket.reject",
  ]),
  helpdesk_t1: new Set([
    "dashboard.view",
    "ticket.read_all",
    "ticket.comment",
    "ticket.attachment_add",
    "ticket.attachment_delete",
    "ticket.update",
    "ticket.assign",
    "ticket.claim",
    "ticket.start",
    "ticket.pending",
    "ticket.escalate",
    "ticket.escalate_functional",
    "ticket.escalate_technical",
    "ticket.resolve",
    "ticket.close",
    "ticket.reopen",
  ]),
  helpdesk_t2: new Set([
    "dashboard.view",
    "ticket.read_all",
    "ticket.comment",
    "ticket.attachment_add",
    "ticket.attachment_delete",
    "ticket.update",
    "ticket.internal_note",
    "ticket.technical_update",
    "ticket.receive_escalated",
    "ticket.start",
    "ticket.pending",
    "ticket.escalate_functional",
    "ticket.escalate_technical",
    "ticket.resolve",
    "ticket.close",
    "ticket.reopen",
  ]),
  manager: new Set([
    "ticket.read_all",
    "ticket.assign",
    "ticket.resolve",
    "ticket.close",
    "ticket.reopen",
    "ticket.update",
    "ticket.delete",
    "ticket.attachment_delete",
    "ticket.comment_manage",
    "ticket.confirm_any",
    "ticket.reject_any",
    "dashboard.view",
    "report.view",
    "user.manage",
  ]),
};

/** Admin implicitly holds every permission code (seed.py grants the full module x action product). */
export function hasPermission(roleCode: string | null, code: string): boolean {
  if (!roleCode) return false;
  if (roleCode === "admin") return true;
  const codes = ROLE_PERMISSION_CODES[roleCode as Exclude<RoleCode, "admin">];
  return codes?.has(code) ?? false;
}
