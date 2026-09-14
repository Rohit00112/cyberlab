"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { LabLogsModal } from "@/components/labs/lab-logs-modal";
import { ApiError, api } from "@/lib/api";
import type { LabAdmin } from "@/lib/challenges/types";

export function TerminateLab({ lab }: { lab: LabAdmin }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showLogs, setShowLogs] = useState(false);

  async function terminate() {
    if (!window.confirm(`Force-expire lab ${lab.container_name ?? lab.id}?`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.post<LabAdmin>(`/admin/labs/${lab.id}/terminate`);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.detail) setError(err.detail);
      else setError("Terminate failed — try again.");
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center justify-end gap-2">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setShowLogs(true)}
      >
        Inspect & Logs
      </Button>
      {lab.status === "running" || lab.status === "provisioning" ? (
        <Button variant="destructive" size="sm" onClick={terminate} disabled={busy}>
          Terminate
        </Button>
      ) : null}
      {error ? <span className="text-xs text-destructive">{error}</span> : null}

      <LabLogsModal
        labId={lab.id}
        isOpen={showLogs}
        onClose={() => setShowLogs(false)}
        title={`${lab.user_display_name ?? "Student"} - ${lab.challenge_title ?? lab.container_name ?? lab.id}`}
      />
    </div>
  );
}

export const LabAdminActions = TerminateLab;