"use client";

import Link from "next/link";

import { useAuth } from "@/components/providers/auth-provider";
import { hasPermission } from "@/lib/auth/client";

export function AppNav() {
  const { user, logout } = useAuth();

  return (
    <header className="border-b">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <Link href="/dashboard" className="font-semibold">
          IIC CyberLab
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          <Link href="/dashboard" className="hover:underline">
            Dashboard
          </Link>
          <Link href="/challenges" className="hover:underline">
            Challenges
          </Link>
          <Link href="/leaderboard" className="hover:underline">
            Leaderboard
          </Link>
          <Link href="/competitions" className="hover:underline">
            Competitions
          </Link>
          {hasPermission("lab.launch") ? (
            <Link href="/labs" className="hover:underline">
              My Labs
            </Link>
          ) : null}
          {hasPermission("analytics.view") ? (
            <Link href="/analytics" className="hover:underline">
              Analytics
            </Link>
          ) : null}
          {hasPermission("challenge.edit") ? (
            <Link href="/admin/challenges" className="hover:underline">
              Manage
            </Link>
          ) : null}
          {hasPermission("user.view") ? (
            <Link href="/admin/users" className="hover:underline">
              Users
            </Link>
          ) : null}
          {hasPermission("lab.admin") ? (
            <Link href="/admin/labs" className="hover:underline">
              Labs
            </Link>
          ) : null}
          {hasPermission("competition.manage") ? (
            <Link href="/admin/competitions" className="hover:underline">
              Comp Admin
            </Link>
          ) : null}
          {hasPermission("audit.view") ? (
            <Link href="/admin/audit" className="hover:underline">
              Audit
            </Link>
          ) : null}
          <Link href="/profile" className="hover:underline">
            Profile
          </Link>
          <span className="text-muted-foreground">{user?.display_name ?? user?.email}</span>
          <button onClick={logout} className="text-muted-foreground hover:text-foreground">
            Sign out
          </button>
        </nav>
      </div>
    </header>
  );
}