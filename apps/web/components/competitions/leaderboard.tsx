"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import type { LeaderboardEntry } from "@/lib/competitions/types";

interface LeaderboardData {
  items: LeaderboardEntry[];
}

export function CompetitionLeaderboard({
  competitionId,
  initial,
}: {
  competitionId: string;
  initial: LeaderboardEntry[];
}) {
  const [items, setItems] = useState<LeaderboardEntry[]>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const data = await api.get<LeaderboardData>(
        `/competitions/${competitionId}/leaderboard`,
        { authenticated: false },
      );
      setItems(data.items);
    } catch (err) {
      if (err instanceof ApiError) setError("Leaderboard unavailable right now.");
      else setError("Leaderboard unavailable right now.");
    } finally {
      setBusy(false);
    }
  }, [competitionId]);

  useEffect(() => {
    const timer = setInterval(refresh, 30_000);
    return () => clearInterval(timer);
  }, [refresh]);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Live rankings — refreshes automatically every 30s.
        </p>
        <Button variant="outline" size="sm" onClick={refresh} disabled={busy}>
          Refresh
        </Button>
      </div>
      {error ? <p className="mb-3 text-sm text-destructive">{error}</p> : null}
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No scores yet. Be the first to solve a challenge.
        </p>
      ) : (
        <table className="w-full text-sm">
          <tbody>
            {items.map((entry) => (
              <tr key={`${entry.entity_type}-${entry.entity_id}`}>
                <td className="py-1.5 pr-3 tabular-nums text-muted-foreground">
                  #{entry.rank}
                </td>
                <td className="py-1.5 pr-3 font-medium">{entry.display_name}</td>
                <td className="py-1.5 pr-3 text-xs text-muted-foreground">
                  {entry.solved_count} solved
                </td>
                <td className="py-1.5 text-right font-semibold tabular-nums">
                  {entry.points}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}