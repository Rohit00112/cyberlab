"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { LabLogsModal } from "@/components/labs/lab-logs-modal";
import { ApiError, api } from "@/lib/api";
import {
  LAB_STATUS_LABELS,
  type Challenge,
  type Lab,
} from "@/lib/challenges/types";

export function LabPanel({
  challenge,
  onActiveLabChange,
}: {
  challenge: Challenge;
  onActiveLabChange?: (lab: Lab | null) => void;
}) {
  const [labs, setLabs] = useState<Lab[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showLogs, setShowLogs] = useState(false);

  useEffect(() => {
    api
      .get<Lab[]>("/labs")
      .then((all) => setLabs(all.filter((lab) => lab.challenge_id === challenge.id)))
      .catch(() => setLabs([]));
  }, [challenge.id]);

  const lab = labs?.[0] ?? null;

  useEffect(() => {
    const active = lab?.status === "running" ? lab : null;
    onActiveLabChange?.(active);
  }, [lab, onActiveLabChange]);

  async function launchLab() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.post<Lab>(`/challenges/${challenge.id}/lab/launch`);
      setLabs((prev) => [created, ...(prev ?? [])]);
    } catch (err) {
      const message = err instanceof ApiError ? err.detail ?? "Launch failed" : "Network error";
      setError(typeof message === "string" ? message : "Launch failed");
    } finally {
      setBusy(false);
    }
  }

  async function act(action: "stop" | "reset" | "expire") {
    if (busy || !lab) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.post<Lab>(`/labs/${lab.id}/${action}`);
      setLabs((prev) => [updated, ...(prev ?? []).filter((l) => l.id !== updated.id)]);
    } catch (err) {
      const message = err instanceof ApiError ? err.detail ?? "Action failed" : "Network error";
      setError(typeof message === "string" ? message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  if (challenge.environment_type === "none") {
    return (
      <p className="text-xs text-muted-foreground">
        This challenge does not use a lab environment — analyze the attached files here instead.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {!lab ? (
        <>
          <Button className="w-full" onClick={launchLab} disabled={busy}>
            {busy ? "Launching…" : "Launch Lab"}
          </Button>
          <p className="text-xs text-muted-foreground">
            Spins up an isolated single-user container on our lab network.
            {challenge.lab_config?.expiry_minutes
              ? ` Expires after ${challenge.lab_config.expiry_minutes} minutes.`
              : " Expires after 60 minutes."}
          </p>
        </>
      ) : (
        <>
          <div className="flex items-center justify-between">
            <Badge variant={lab.status === "running" ? "default" : "outline"}>
              {LAB_STATUS_LABELS[lab.status]}
            </Badge>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost" onClick={() => setShowLogs(true)}>
                Logs
              </Button>
              {lab.status === "running" ? (
                <Button size="sm" variant="outline" onClick={() => act("stop")} disabled={busy}>
                  Stop
                </Button>
              ) : (
                <Button size="sm" variant="outline" onClick={() => act("reset")} disabled={busy}>
                  Reset
                </Button>
              )}
            </div>
          </div>
          <LabLogsModal
            labId={lab.id}
            isOpen={showLogs}
            onClose={() => setShowLogs(false)}
            title={challenge.title}
          />
          {lab.status === "provisioning" ? (
            <p className="text-xs text-muted-foreground">
              Container is starting — refresh shortly or hit Reset.
            </p>
          ) : null}
          {lab.status === "error" && lab.error_message ? (
            <p className="text-xs text-destructive">{lab.error_message}</p>
          ) : null}
          {lab.status === "running" && lab.connection_hint ? (
            <pre className="rounded-md border bg-muted/50 p-2 text-xs leading-relaxed whitespace-pre-wrap">
              {lab.connection_hint}
            </pre>
          ) : null}
          {lab.status === "stopped" ? (
            <p className="text-xs text-muted-foreground">
              Stopped. Reset to relaunch and get a fresh environment.
            </p>
          ) : null}
          {lab.status === "expired" ? (
            <p className="text-xs text-muted-foreground">
              Expired. Reset to launch a fresh environment.
            </p>
          ) : null}
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
        </>
      )}
    </div>
  );
}