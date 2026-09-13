"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { RequireAuth } from "@/components/providers/require-auth";
import { useAuth } from "@/components/providers/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, api } from "@/lib/api";
import { LAB_STATUS_LABELS, type Lab } from "@/lib/challenges/types";

export default function LabsPage() {
  const { user } = useAuth();
  const [labs, setLabs] = useState<Lab[] | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Lab[]>("/labs")
      .then(setLabs)
      .catch(() => setLabs([]));
  }, []);

  async function act(lab: Lab, action: "stop" | "reset" | "expire") {
    setBusyId(lab.id);
    setError(null);
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

  return (
    <RequireAuth>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <h1 className="text-2xl font-semibold">My labs</h1>
        <p className="mt-2 text-muted-foreground">
          Isolated single-user environments provisioned per challenge. Expire 60 minutes after
          launch — Reset for a fresh one.
        </p>
        {error ? <p className="mt-4 text-sm text-destructive">{error}</p> : null}
        <div className="mt-6 grid gap-4">
          {labs === null ? (
            <p className="text-muted-foreground">Loading…</p>
          ) : labs.length === 0 ? (
            <Card>
              <CardContent className="pt-6 text-muted-foreground">
                No labs yet. Open a challenge with a lab environment and hit "Launch Lab".
              </CardContent>
            </Card>
          ) : (
            labs.map((lab) => (
              <Card key={lab.id}>
                <CardHeader className="flex-row items-center justify-between">
                  <CardTitle className="text-base">
                    {lab.challenge_title ?? "Challenge"}
                  </CardTitle>
                  <Badge variant={lab.status === "running" ? "default" : "outline"}>
                    {LAB_STATUS_LABELS[lab.status]}
                  </Badge>
                </CardHeader>
                <CardContent className="space-y-3 pt-2">
                  {lab.status === "error" && lab.error_message ? (
                    <p className="text-sm text-destructive">{lab.error_message}</p>
                  ) : null}
                  {lab.status === "running" && lab.connection_hint ? (
                    <pre className="rounded-md border bg-muted/50 p-2 text-xs leading-relaxed whitespace-pre-wrap">
                      {lab.connection_hint}
                    </pre>
                  ) : null}
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-muted-foreground">
                      {lab.network_name} · {lab.expires_at ? `expires ${lab.expires_at.replace("T", " ").slice(0, 16)} UTC` : ""}
                    </p>
                    <div className="flex gap-2">
                      {lab.status === "running" ? (
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
                          disabled={busyId === lab.id}
                          onClick={() => act(lab, "reset")}
                        >
                          Reset
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={busyId === lab.id}
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
            ))
          )}
        </div>
        <p className="mt-6 text-xs text-muted-foreground">
          Signed in as {user?.display_name ?? "student"}.
        </p>
      </main>
    </RequireAuth>
  );
}