"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError, api } from "@/lib/api";
import type { Challenge } from "@/lib/challenges/types";
import type { CompetitionChallengeEntry } from "@/lib/competitions/types";

export function CompetitionChallengePicker({
  competitionId,
  current,
  available,
}: {
  competitionId: string;
  current: CompetitionChallengeEntry[];
  available: Challenge[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentIds = new Set(current.map((e) => e.challenge.id));
  const options = available.filter((ch) => !currentIds.has(ch.id));
  const [selectedId, setSelectedId] = useState<string>("");

  async function add() {
    if (!selectedId) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/competitions/${competitionId}/challenges`, {
        challenge_id: selectedId,
      });
      setSelectedId("");
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.detail) setError(err.detail);
      else setError("Failed to add challenge.");
      setBusy(false);
    }
  }

  async function remove(challengeId: string) {
    setBusy(true);
    setError(null);
    try {
      await api.delete(`/competitions/${competitionId}/challenges/${challengeId}`);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.detail) setError(err.detail);
      else setError("Failed to remove challenge.");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {current.length === 0 ? (
        <p className="text-sm text-muted-foreground">No challenges added yet.</p>
      ) : (
        <ul className="space-y-1.5">
          {current.map((entry) => (
            <li
              key={entry.challenge.id}
              className="flex items-center justify-between gap-2 rounded border px-3 py-1.5 text-sm"
            >
              <div className="min-w-0">
                <span className="font-medium">{entry.challenge.title}</span>
                <span className="ml-2 text-xs text-muted-foreground">
                  {entry.challenge.category} · {entry.points ?? entry.challenge.points} pts
                </span>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void remove(entry.challenge.id)}
                disabled={busy}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}

      {options.length > 0 ? (
        <div className="flex items-center gap-2">
          <Select value={selectedId} onValueChange={(value) => value && setSelectedId(value)}>
            <SelectTrigger className="w-full max-w-sm">
              <SelectValue placeholder="Add a challenge" />
            </SelectTrigger>
            <SelectContent>
              {options.map((ch) => (
                <SelectItem key={ch.id} value={ch.id}>
                  {ch.title} ({ch.points} pts)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button onClick={() => void add()} disabled={busy || !selectedId}>
            Add
          </Button>
        </div>
      ) : null}

      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}