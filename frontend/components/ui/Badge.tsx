"use client";

import { useTranslations } from "next-intl";

/**
 * Status/priority pill that reads its color straight from the API
 * (TicketStatus.color / TicketPriority.color) rather than a hardcoded
 * palette, since that config is backend-owned. Falls back to ink-500
 * grey if the record has no color set.
 */
export function ColorBadge({ label, color }: { label: string; color: string | null }) {
  const hex = color ?? "#56698c";
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium"
      style={{
        color: hex,
        backgroundColor: `${hex}1a`,
        border: `1px solid ${hex}40`,
      }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: hex }} />
      {label}
    </span>
  );
}

export function RoleBadge({ code }: { code: string }) {
  const t = useTranslations("role");
  const label = t.has(code) ? t(code) : code;
  return (
    <span className="inline-flex items-center rounded-full bg-ink-800 px-2.5 py-0.5 text-xs font-medium text-ink-100">
      {label}
    </span>
  );
}
