"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { listUsers } from "@/lib/api/users";
import { apiErrorMessage } from "@/lib/api/client";
import type { UserResponse } from "@/lib/types";
import { fullName } from "@/lib/types";
import { PageHeader } from "@/components/ui/PageHeader";
import { ApiErrorState } from "@/components/ui/ApiErrorState";
import { RoleBadge } from "@/components/ui/Badge";

// Gated by role in the UI for a clean redirect/empty-state experience —
// but the real authorization boundary is server-side: GET /users itself
// requires the `user.manage` permission (require_permission in
// app/api/v1/users.py), so a non-admin hitting this page directly still
// gets a 403 from the API, not just a hidden nav link.
export default function AdminPage() {
  const { roleCode } = useAuth();
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setUsers(await listUsers());
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't load users — you may not have user.manage permission"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (roleCode !== "admin") {
    return (
      <ApiErrorState message="Admin tools are only available to the admin role." />
    );
  }

  return (
    <div>
      <PageHeader title="Users" description="Everyone with an account on this platform." />

      <div className="overflow-hidden rounded-card border border-ink-100 bg-white">
        {loading && <p className="px-5 py-8 text-center text-sm text-ink-500">Loading…</p>}
        {error && (
          <div className="p-5">
            <ApiErrorState message={error} onRetry={load} />
          </div>
        )}
        {!loading && !error && (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-ink-100 bg-ink-50 text-xs font-medium uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-5 py-3">Name</th>
                <th className="px-5 py-3">Email</th>
                <th className="px-5 py-3">Roles</th>
                <th className="px-5 py-3">Department</th>
                <th className="px-5 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-ink-50">
                  <td className="px-5 py-3 font-medium text-ink-950">{fullName(user)}</td>
                  <td className="px-5 py-3 text-ink-700">{user.email}</td>
                  <td className="px-5 py-3">
                    <div className="flex flex-wrap gap-1">
                      {user.roles.map((r) => (
                        <RoleBadge key={r.id} code={r.code} />
                      ))}
                    </div>
                  </td>
                  <td className="px-5 py-3 text-ink-700">{user.department?.name ?? "—"}</td>
                  <td className="px-5 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        user.is_active ? "bg-green-100 text-green-700" : "bg-ink-100 text-ink-500"
                      }`}
                    >
                      {user.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
