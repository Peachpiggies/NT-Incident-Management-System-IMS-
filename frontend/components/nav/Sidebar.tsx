"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/auth/AuthProvider";
import { fullName } from "@/lib/types";
import { RoleBadge } from "@/components/ui/Badge";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/tickets", label: "Tickets" },
];

const ADMIN_NAV = [{ href: "/admin", label: "Admin" }];

export function Sidebar() {
  const pathname = usePathname();
  const { user, roleCode, logout } = useAuth();

  const items = roleCode === "admin" ? [...NAV, ...ADMIN_NAV] : NAV;

  return (
    <aside className="flex h-screen w-60 flex-col justify-between border-r border-ink-100 bg-ink-950 text-ink-100">
      <div>
        <div className="px-5 py-5">
          <p className="text-sm font-semibold tracking-tight text-white">NT-IMS</p>
          <p className="text-xs text-ink-300">Incident Management</p>
        </div>
        <nav className="mt-2 flex flex-col gap-1 px-3">
          {items.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                  active ? "bg-accent-600 text-white" : "text-ink-300 hover:bg-ink-800 hover:text-white"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      {user && (
        <div className="border-t border-ink-800 p-4">
          <p className="truncate text-sm font-medium text-white">{fullName(user)}</p>
          <p className="truncate text-xs text-ink-300">{user.email}</p>
          {roleCode && (
            <div className="mt-2">
              <RoleBadge code={roleCode} />
            </div>
          )}
          <button
            onClick={() => void logout()}
            className="mt-3 w-full rounded-md border border-ink-700 px-3 py-1.5 text-xs font-medium text-ink-300 hover:border-ink-500 hover:text-white"
          >
            Sign out
          </button>
        </div>
      )}
    </aside>
  );
}
