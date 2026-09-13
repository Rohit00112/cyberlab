"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import type { Competition } from "@/lib/competitions/types";

const REGISTRATION_OPEN = new Set(["registration", "scheduled"]);

export function CompetitionRegisterCard({ competition }: { competition: Competition }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const status = competition.status;
  const me = competition.me;
  const registered = me?.registered ?? false;
  const team = me?.team ?? null;

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.detail) setError(err.detail);
      else setError("Something went wrong — try again.");
      setBusy(false);
    }
  }

  function register() {
    void run(() => api.post<Competition>(`/competitions/${competition.id}/register`));
  }

  function unregister() {
    if (!window.confirm("Leave this competition? Your submissions stay.")) return;
    void run(() => api.post<Competition>(`/competitions/${competition.id}/unregister`));
  }

  function createTeam() {
    if (name.trim().length < 2) return setError("Team name must be at least 2 characters.");
    void run(() =>
      api.post<Competition>(`/competitions/${competition.id}/teams`, { name: name.trim() }),
    );
  }

  return (
    <div className="rounded-lg border p-4">
      <h2 className="font-medium">Participation</h2>
      {registered ? (
        <p className="mt-1 text-sm text-muted-foreground">
          You&apos;re registered
          {team ? (
            <>
              {" "}
              for team <span className="font-medium">{team.name}</span> (
              {team.member_count} member{team.member_count === 1 ? "" : "s"})
            </>
          ) : (
            "."
          )}
        </p>
      ) : (
        <p className="mt-1 text-sm text-muted-foreground">
          {REGISTRATION_OPEN.has(status)
            ? "Registration is open — save your spot."
            : "You are not registered."}
        </p>
      )}

      {error ? <p className="mt-2 text-sm text-destructive">{error}</p> : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {!registered && REGISTRATION_OPEN.has(status) ? (
          <Button onClick={register} disabled={busy}>
            Register
          </Button>
        ) : null}
        {registered && REGISTRATION_OPEN.has(status) ? (
          <Button variant="outline" onClick={unregister} disabled={busy}>
            Unregister
          </Button>
        ) : null}
        {registered && competition.allow_teams && !team && REGISTRATION_OPEN.has(status) ? (
          <div className="flex w-full items-center gap-2 sm:w-auto">
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Team name"
              className="max-w-48"
            />
            <Button onClick={createTeam} disabled={busy}>
              Create team
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}