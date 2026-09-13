"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import {
  COMPETITION_ACTION_LABELS,
  COMPETITION_ACTIONS,
  type Competition,
} from "@/lib/competitions/types";

export function CompetitionAdminActions({ competition }: { competition: Competition }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const actions = COMPETITION_ACTIONS[competition.status] ?? [];
  const canFreeze =
    competition.status === "live" || competition.status === "scheduled";

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.detail) setError(err.detail);
      else setError("Action failed — try again.");
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {actions.map((action) => (
        <Button
          key={action}
          variant={action === "start" || action === "archive" ? "destructive" : "default"}
          size="sm"
          disabled={busy}
          onClick={() =>
            run(() =>
              api.post<Competition>(`/competitions/${competition.id}/transition`, {
                action,
              }),
            )
          }
        >
          {COMPETITION_ACTION_LABELS[action]}
        </Button>
      ))}
      {canFreeze ? (
        competition.freeze_leaderboard ? (
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() =>
              run(() => api.post<Competition>(`/competitions/${competition.id}/unfreeze`))
            }
          >
            Unfreeze leaderboard
          </Button>
        ) : (
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() =>
              run(() => api.post<Competition>(`/competitions/${competition.id}/freeze`))
            }
          >
            Freeze leaderboard
          </Button>
        )
      ) : null}
      {error ? <span className="text-xs text-destructive">{error}</span> : null}
    </div>
  );
}