"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { RequireAuth } from "@/components/providers/require-auth";
import { useAuth } from "@/components/providers/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LabLogsModal } from "@/components/labs/lab-logs-modal";
import { ApiError, api } from "@/lib/api";
import { LAB_STATUS_LABELS, type Lab } from "@/lib/challenges/types";

export default function LabsPage() {
  const { user } = useAuth();
  const [labs, setLabs] = useState<Lab[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [activeLogLab, setActiveLogLab] = useState<Lab | null>(null);

  useEffect(() => {
    api
      .get<Lab[]>("/labs")
      .then(setLabs)
      .catch(() => setLabs([]));
  }, []);

  const activeLabIds =
    labs
      ?.filter((l) => ["queued", "provisioning", "starting", "resetting"].includes(l.status))
      .map((l) => `${l.id}:${l.status}`)
      .join(",") ?? "";

  // SSE Real-time updates for active/provisioning labs
  useEffect(() => {
    if (!labs || labs.length === 0) return;
    const activeLabs = labs.filter((l) =>
      ["queued", "provisioning", "starting", "resetting"].includes(l.status)
    );
    if (activeLabs.length === 0) return;

    const sources: EventSource[] = [];
    activeLabs.forEach((lab) => {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
      const es = new EventSource(`${apiBase}/labs/${lab.id}/events`, { withCredentials: true });
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setLabs((prev) =>
            (prev ?? []).map((l) =>
              l.id === data.id
                ? {
                    ...l,
                    status: data.status,
                    connection_hint: data.connection_hint,
                    error_message: data.error_message,
                    expires_at: data.expires_at,
                  }
                : l
            )
          );
          if (["running", "failed", "stopped", "expired"].includes(data.status)) {
            es.close();
          }
        } catch {
          // ignore parse error
        }
      };
      sources.push(es);
    });

    return () => {
      sources.forEach((es) => es.close());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeLabIds]);

  async function act(lab: Lab, action: "stop" | "reset" | "expire") {
    setBusyId(lab.id);
    setError(null);
    setSuccess(null);
    try {
      const updated = await api.post<Lab>(`/labs/${lab.id}/${action}`);
      setLabs((prev) => (prev ?? []).map((l) => (l.id === updated.id ? updated : l)));
    } catch (err) {
      const message = err instanceof ApiError ? err.detail ?? "Action failed" : "Network error";
      setError(typeof message === "string" ? message : "Action failed");
    } finally {
      setBusyId(null);
    }
  }

  async function extendLease(lab: Lab) {
    setBusyId(lab.id);
    setError(null);
    setSuccess(null);
    try {
      const updated = await api.put<Lab>(`/labs/${lab.id}/extend`, { additional_minutes: 30 });
      setLabs((prev) => (prev ?? []).map((l) => (l.id === updated.id ? updated : l)));
      setSuccess("Lease extended by 30 minutes.");
    } catch (err) {
      const message = err instanceof ApiError ? err.detail ?? "Failed to extend lease" : "Network error";
      setError(typeof message === "string" ? message : "Failed to extend lease");
    } finally {
      setBusyId(null);
    }
  }

  function downloadVpnConfig() {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
    window.open(`${apiBase}/vpn/download`, "_blank");
  }

  return (
    <RequireAuth>
      <div className="contents">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">My labs</h1>
            <p className="mt-1 text-muted-foreground">
              Isolated environments provisioned per challenge with real-time lifecycle monitoring.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={downloadVpnConfig}>
            Download WireGuard VPN (.conf)
          </Button>
        </div>

        {error ? <p className="mt-4 text-sm text-destructive">{error}</p> : null}
        {success ? <p className="mt-4 text-sm text-emerald-500">{success}</p> : null}

        <div className="mt-6 grid gap-4">
          {labs === null ? (
            <p className="text-muted-foreground">Loading…</p>
          ) : labs.length === 0 ? (
            <Card>
              <CardContent className="pt-6 text-muted-foreground">
                No labs yet. Open a challenge with a lab environment and press the Launch
                Lab button on its detail page.
              </CardContent>
            </Card>
          ) : (
            labs.map((lab) => {
              const isRunning = lab.status === "running";
              const isProvisioning = ["queued", "provisioning", "starting", "resetting"].includes(lab.status);

              return (
                <Card key={lab.id}>
                  <CardHeader className="flex-row items-center justify-between">
                    <CardTitle className="text-base">
                      {lab.challenge_title ?? "Challenge"}
                    </CardTitle>
                    <div className="flex items-center gap-2">
                      {isProvisioning && (
                        <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-500" />
                      )}
                      <Badge
                        variant={
                          isRunning
                            ? "default"
                            : isProvisioning
                            ? "secondary"
                            : "outline"
                        }
                      >
                        {LAB_STATUS_LABELS[lab.status] ?? lab.status}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3 pt-2">
                    {lab.status === "failed" || lab.status === "error" ? (
                      <p className="text-sm text-destructive">{lab.error_message || "Lab encountered an error"}</p>
                    ) : null}
                    {isRunning && lab.connection_hint ? (
                      <pre className="rounded-md border bg-muted/50 p-2 text-xs leading-relaxed whitespace-pre-wrap">
                        {lab.connection_hint}
                      </pre>
                    ) : null}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <p className="text-xs text-muted-foreground">
                        {lab.network_name} · {lab.expires_at ? `expires ${lab.expires_at.replace("T", " ").slice(0, 16)} UTC` : ""}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setActiveLogLab(lab)}
                        >
                          Logs
                        </Button>
                        {isRunning && (
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={busyId === lab.id}
                            onClick={() => extendLease(lab)}
                          >
                            +30m Lease
                          </Button>
                        )}
                        {isRunning ? (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={busyId === lab.id}
                            onClick={() => act(lab, "stop")}
                          >
                            Stop
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={busyId === lab.id || isProvisioning}
                            onClick={() => act(lab, "reset")}
                          >
                            Reset
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={busyId === lab.id || isProvisioning}
                          onClick={() => act(lab, "expire")}
                        >
                          Expire
                        </Button>
                        <Link href={`/challenges/${lab.challenge_id}`}>
                          <Button size="sm">Open challenge</Button>
                        </Link>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })
          )}
        </div>
        <LabLogsModal
          labId={activeLogLab?.id ?? ""}
          isOpen={Boolean(activeLogLab)}
          onClose={() => setActiveLogLab(null)}
          title={activeLogLab?.challenge_title ?? undefined}
        />
        <p className="mt-6 text-xs text-muted-foreground">
          Signed in as {user?.display_name ?? "student"}.
        </p>
      </div>
    </RequireAuth>
  );
}