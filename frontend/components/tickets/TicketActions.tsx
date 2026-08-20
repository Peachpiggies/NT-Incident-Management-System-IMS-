"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/components/auth/AuthProvider";
import { hasPermission } from "@/lib/permissions";
import { apiErrorMessage } from "@/lib/api/client";
import { listDepartments } from "@/lib/api/references";
import { listUsers } from "@/lib/api/users";
import {
  assignTicket,
  claimTicket,
  closeTicket,
  confirmTicket,
  escalateTicket,
  escalateTicketFunctional,
  escalateTicketTechnical,
  pendingTicket,
  receiveEscalatedTicket,
  reopenTicket,
  rejectTicket,
  resolveTicket,
  startTicket,
} from "@/lib/api/tickets";
import type {
  DepartmentSummary,
  TicketResponse,
  TicketTechnicalReasonCode,
  UserResponse,
} from "@/lib/types";
import { fullName } from "@/lib/types";

const TECHNICAL_REASON_CODES: TicketTechnicalReasonCode[] = [
  "SKILL_REQUIRED",
  "COMPLEXITY",
  "ACCESS_REQUIRED",
  "SYSTEM_DEPENDENCY",
  "UNRESOLVED_AFTER_ATTEMPTS",
  "SLA_RISK",
  "MDDR_RISK",
];

const MAX_TIER = 3;

// Mirrors currentStepFromTicket() in tickets/[id]/page.tsx and the backend's
// TIER_ROLE_CODE (services/escalation.py): which role currently "holds" a
// ticket for a given tier. Used below to hide the two escalate buttons from
// roles that aren't actually holding the ticket right now -- e.g. Helpdesk
// T1 shouldn't see "Escalate to next tier" once a ticket has moved on to T2.
// This is UI-only convenience; the backend enforces the real check
// (_require_current_tier_holder) regardless of what this hides or shows.
function isCurrentTierHolder(ticket: TicketResponse, roleCode: string | null): boolean {
  if (roleCode === "admin") return true;
  const tier = Math.min(ticket.current_tier, MAX_TIER);
  if (tier <= 1) return roleCode === "helpdesk_t1";
  if (tier === 2) return roleCode === "helpdesk_t2";
  return roleCode === "manager";
}

function buttonClass(variant: "primary" | "secondary" | "danger" = "secondary") {
  const base = "rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-60";
  if (variant === "primary") return `${base} bg-accent-600 text-white hover:bg-accent-500`;
  if (variant === "danger") return `${base} bg-red-600 text-white hover:bg-red-500`;
  return `${base} border border-ink-100 bg-white text-ink-700 hover:bg-ink-50`;
}

type ModalKind = "assign" | "escalateFunctional" | "escalateTechnical" | "reject" | null;

export function TicketActions({
  ticket,
  onUpdated,
}: {
  ticket: TicketResponse;
  onUpdated: () => void;
}) {
  const t = useTranslations("ticketActions");
  const { user, roleCode } = useAuth();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalKind>(null);

  const statusName = ticket.status.name;
  const isRequester = user?.id === ticket.requester_id;
  const can = (code: string) => hasPermission(roleCode, code);

  const claimLockedForMe =
    ticket.escalation_locked_department_id !== null &&
    user?.department?.id === ticket.escalation_locked_department_id;

  async function run(key: string, action: () => Promise<unknown>) {
    setError(null);
    setBusy(key);
    try {
      await action();
      onUpdated();
    } catch (err) {
      setError(apiErrorMessage(err, t("errorFallback")));
    } finally {
      setBusy(null);
    }
  }

  const actions: { key: string; label: string; onClick: () => void; variant?: "primary" | "secondary" | "danger"; disabled?: boolean; title?: string }[] = [];

  if (can("ticket.claim") && !ticket.assigned_to) {
    actions.push({
      key: "claim",
      label: t("claim"),
      onClick: () => run("claim", () => claimTicket(ticket.id)),
      variant: "primary",
      disabled: claimLockedForMe,
      title: claimLockedForMe
        ? t("claimLockedTooltip", {
            department: ticket.escalation_locked_department?.name ?? "",
          })
        : undefined,
    });
  }

  if (can("ticket.assign") && can("user.manage")) {
    actions.push({ key: "assign", label: t("assign"), onClick: () => setModal("assign") });
  }

  if (can("ticket.start") && (statusName === "Assigned" || statusName === "Pending")) {
    actions.push({
      key: "start",
      label: t("start"),
      onClick: () => run("start", () => startTicket(ticket.id)),
      variant: "primary",
    });
  }

  if (can("ticket.pending") && statusName === "In Progress") {
    actions.push({ key: "pending", label: t("pending"), onClick: () => run("pending", () => pendingTicket(ticket.id)) });
  }

  if (can("ticket.escalate") && (statusName === "Assigned" || statusName === "In Progress")) {
    actions.push({
      key: "escalate",
      label: t("escalate"),
      onClick: () => run("escalate", () => escalateTicket(ticket.id)),
    });
  }

  if (
    can("ticket.escalate_functional") &&
    statusName !== "Closed" &&
    isCurrentTierHolder(ticket, roleCode)
  ) {
    actions.push({
      key: "escalateFunctional",
      label: t("escalateFunctional"),
      onClick: () => setModal("escalateFunctional"),
    });
  }

  if (
    can("ticket.escalate_technical") &&
    statusName !== "Closed" &&
    ticket.current_tier < MAX_TIER &&
    isCurrentTierHolder(ticket, roleCode)
  ) {
    actions.push({
      key: "escalateTechnical",
      label: t("escalateTechnical"),
      onClick: () => setModal("escalateTechnical"),
    });
  }

  if (
    can("ticket.receive_escalated") &&
    statusName === "Escalated" &&
    isCurrentTierHolder(ticket, roleCode)
  ) {
    actions.push({
      key: "receive",
      label: t("receive"),
      onClick: () => run("receive", () => receiveEscalatedTicket(ticket.id)),
      variant: "primary",
    });
  }

  if (can("ticket.resolve") && statusName === "In Progress") {
    actions.push({
      key: "resolve",
      label: t("resolve"),
      onClick: () => run("resolve", () => resolveTicket(ticket.id)),
      variant: "primary",
    });
  }

  if (can("ticket.close") && statusName === "Resolved") {
    actions.push({ key: "close", label: t("close"), onClick: () => run("close", () => closeTicket(ticket.id)) });
  }

  if (can("ticket.reopen") && (statusName === "Resolved" || statusName === "Closed")) {
    actions.push({ key: "reopen", label: t("reopen"), onClick: () => run("reopen", () => reopenTicket(ticket.id)) });
  }

  const canConfirm = (can("ticket.confirm") && isRequester) || can("ticket.confirm_any");
  const canReject = (can("ticket.reject") && isRequester) || can("ticket.reject_any");

  if (canConfirm && statusName === "Resolved") {
    actions.push({
      key: "confirm",
      label: t("confirm"),
      onClick: () => run("confirm", () => confirmTicket(ticket.id)),
      variant: "primary",
    });
  }

  if (canReject && statusName === "Resolved") {
    actions.push({ key: "reject", label: t("reject"), onClick: () => setModal("reject"), variant: "danger" });
  }

  if (actions.length === 0 && !modal) return null;

  return (
    <div className="rounded-card border border-ink-100 bg-white p-5">
      <p className="mb-3 text-sm font-medium text-ink-950">{t("title")}</p>
      {error && <p className="mb-3 text-sm font-medium text-red-600">{error}</p>}
      {claimLockedForMe && (
        <p className="mb-3 flex items-center gap-1.5 rounded-md bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800">
          <span aria-hidden="true">🔒</span>
          {t("claimLockedBanner", {
            department: ticket.escalation_locked_department?.name ?? "",
          })}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {actions.map((a) => (
          <button
            key={a.key}
            disabled={busy !== null || a.disabled}
            title={a.title}
            onClick={a.onClick}
            className={buttonClass(a.variant)}
          >
            {busy === a.key ? t("working") : a.label}
          </button>
        ))}
      </div>

      {modal === "assign" && (
        <AssignModal
          ticketId={ticket.id}
          onClose={() => setModal(null)}
          onDone={() => {
            setModal(null);
            onUpdated();
          }}
        />
      )}
      {modal === "escalateFunctional" && (
        <FunctionalEscalationModal
          ticketId={ticket.id}
          onClose={() => setModal(null)}
          onDone={() => {
            setModal(null);
            onUpdated();
          }}
        />
      )}
      {modal === "escalateTechnical" && (
        <TechnicalEscalationModal
          ticketId={ticket.id}
          currentTier={ticket.current_tier}
          onClose={() => setModal(null)}
          onDone={() => {
            setModal(null);
            onUpdated();
          }}
        />
      )}
      {modal === "reject" && (
        <RejectModal
          ticketId={ticket.id}
          onClose={() => setModal(null)}
          onDone={() => {
            setModal(null);
            onUpdated();
          }}
        />
      )}
    </div>
  );
}

// ===================== Modal shell =====================

function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md rounded-card border border-ink-100 bg-white p-5 shadow-lg">
        <div className="mb-4 flex items-center justify-between">
          <p className="text-sm font-medium text-ink-950">{title}</p>
          <button onClick={onClose} className="text-sm text-ink-500 hover:text-ink-800">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

const fieldClass =
  "rounded-md border border-ink-100 px-3 py-2 text-sm outline-none focus:border-accent-500 w-full";
const labelClass = "flex flex-col gap-1.5 text-xs font-medium text-ink-500";

// ===================== Assign modal (dispatcher: pick any user) =====================

function AssignModal({ ticketId, onClose, onDone }: { ticketId: string; onClose: () => void; onDone: () => void }) {
  const t = useTranslations("ticketActions");
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [assigneeId, setAssigneeId] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void listUsers().then(setUsers).catch(() => setUsers([]));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!assigneeId) return;
    setSubmitting(true);
    setError(null);
    try {
      await assignTicket(ticketId, { assignee_id: assigneeId, reason: reason || null });
      onDone();
    } catch (err) {
      setError(apiErrorMessage(err, t("errorFallback")));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell title={t("assign")} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <label className={labelClass}>
          <span>{t("assignee")}</span>
          <select required value={assigneeId} onChange={(e) => setAssigneeId(e.target.value)} className={fieldClass}>
            <option value="">{t("select")}</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {fullName(u)}
              </option>
            ))}
          </select>
        </label>
        <label className={labelClass}>
          <span>{t("reasonOptional")}</span>
          <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} className={fieldClass} />
        </label>
        {error && <p className="text-sm font-medium text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className={buttonClass()}>
            {t("cancel")}
          </button>
          <button type="submit" disabled={submitting || !assigneeId} className={buttonClass("primary")}>
            {submitting ? t("working") : t("assign")}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

// ===================== Functional escalation modal (re-route to a team) =====================

function FunctionalEscalationModal({
  ticketId,
  onClose,
  onDone,
}: {
  ticketId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const t = useTranslations("ticketActions");
  const [departments, setDepartments] = useState<DepartmentSummary[]>([]);
  const [departmentId, setDepartmentId] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    void listDepartments().then(setDepartments).catch(() => setDepartments([]));
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!departmentId) return;
    setSubmitting(true);
    setError(null);
    try {
      await escalateTicketFunctional(ticketId, {
        to_department_id: departmentId,
        comment: comment || null,
      });
      onDone();
    } catch (err) {
      setError(apiErrorMessage(err, t("errorFallback")));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell title={t("escalateFunctional")} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <label className={labelClass}>
          <span>{t("targetDepartment")}</span>
          <select
            required
            value={departmentId}
            onChange={(e) => setDepartmentId(e.target.value)}
            className={fieldClass}
          >
            <option value="">{t("select")}</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </label>
        <label className={labelClass}>
          <span>{t("commentOptional")}</span>
          <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} className={fieldClass} />
        </label>
        {error && <p className="text-sm font-medium text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className={buttonClass()}>
            {t("cancel")}
          </button>
          <button type="submit" disabled={submitting || !departmentId} className={buttonClass("primary")}>
            {submitting ? t("working") : t("escalateFunctional")}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

// ===================== Technical escalation modal (move up the tier chain) =====================

function TechnicalEscalationModal({
  ticketId,
  currentTier,
  onClose,
  onDone,
}: {
  ticketId: string;
  currentTier: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const t = useTranslations("ticketActions");
  const tOptions = useTranslations("ticketActions.reasonCode");
  const nextTier = Math.min(currentTier + 1, MAX_TIER);
  const tierOptions = Array.from({ length: MAX_TIER - currentTier }, (_, i) => currentTier + 1 + i);

  const [toTier, setToTier] = useState(nextTier);
  const [reasonCode, setReasonCode] = useState<TicketTechnicalReasonCode>("SKILL_REQUIRED");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await escalateTicketTechnical(ticketId, {
        to_tier: toTier,
        reason_code: reasonCode,
        comment: comment || null,
        allow_tier_skip: toTier > currentTier + 1,
      });
      onDone();
    } catch (err) {
      setError(apiErrorMessage(err, t("errorFallback")));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell title={t("escalateTechnical")} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <label className={labelClass}>
          <span>{t("targetTier")}</span>
          <select
            value={toTier}
            onChange={(e) => setToTier(Number(e.target.value))}
            className={fieldClass}
          >
            {tierOptions.map((tier) => (
              <option key={tier} value={tier}>
                {t("tier", { tier })}
              </option>
            ))}
          </select>
        </label>
        <label className={labelClass}>
          <span>{t("reasonCodeLabel")}</span>
          <select
            required
            value={reasonCode}
            onChange={(e) => setReasonCode(e.target.value as TicketTechnicalReasonCode)}
            className={fieldClass}
          >
            {TECHNICAL_REASON_CODES.map((code) => (
              <option key={code} value={code}>
                {tOptions(code)}
              </option>
            ))}
          </select>
        </label>
        <label className={labelClass}>
          <span>{t("commentOptional")}</span>
          <textarea rows={3} value={comment} onChange={(e) => setComment(e.target.value)} className={fieldClass} />
        </label>
        {error && <p className="text-sm font-medium text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className={buttonClass()}>
            {t("cancel")}
          </button>
          <button type="submit" disabled={submitting} className={buttonClass("primary")}>
            {submitting ? t("working") : t("escalateTechnical")}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}

// ===================== Reject modal (customer sends resolution back) =====================

function RejectModal({ ticketId, onClose, onDone }: { ticketId: string; onClose: () => void; onDone: () => void }) {
  const t = useTranslations("ticketActions");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!reason.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await rejectTicket(ticketId, { reason });
      onDone();
    } catch (err) {
      setError(apiErrorMessage(err, t("errorFallback")));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell title={t("reject")} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <label className={labelClass}>
          <span>{t("reasonRequired")}</span>
          <textarea
            required
            minLength={1}
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className={fieldClass}
          />
        </label>
        {error && <p className="text-sm font-medium text-red-600">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className={buttonClass()}>
            {t("cancel")}
          </button>
          <button type="submit" disabled={submitting || !reason.trim()} className={buttonClass("danger")}>
            {submitting ? t("working") : t("reject")}
          </button>
        </div>
      </form>
    </ModalShell>
  );
}