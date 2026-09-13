"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import type { AdminUser } from "@/lib/challenges/types";

export function UserToggle({ user }: { user: AdminUser }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      await api.patch<AdminUser>(`/users/${user.id}`, {
        is_active: !user.is_active,
      });
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.detail) setError(err.detail);
      else setError("Action failed — try again.");
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center justify-end gap-2">
      <Button
        variant={user.is_active ? "outline" : "default"}
        size="sm"
        onClick={toggle}
        disabled={busy}
      >
        {user.is_active ? "Suspend" : "Activate"}
      </Button>
      {error ? <span className="text-xs text-destructive">{error}</span> : null}
    </div>
  );
}