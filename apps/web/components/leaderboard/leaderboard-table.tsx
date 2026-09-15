"use client";

import Link from "next/link";

import { useAuth } from "@/components/providers/auth-provider";
import { cn } from "@/lib/utils";
import type { LeaderboardEntry } from "@/lib/challenges/types";
import { TrophyIcon } from "lucide-react";

const MEDALS = ["text-amber-500", "text-zinc-400", "text-orange-600"];

function initialsOf(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function LeaderboardTable({ entries }: { entries: LeaderboardEntry[] }) {
  const { user } = useAuth();
  const maxPoints = Math.max(...entries.map((e) => e.points), 1);

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border bg-muted/40 px-4 py-3">
        <TrophyIcon className="size-4 text-primary" />
        <p className="text-sm font-semibold">Global ranking</p>
        <span className="ml-auto text-xs text-muted-foreground tabular-nums">
          {entries.length} players
        </span>
      </div>
      <div className="divide-y divide-border/70">
        {entries.map((entry) => {
          const isTop = entry.rank <= 3;
          const isYou = entry.user_id === user?.id;
          return (
            <div
              key={entry.user_id}
              className={cn(
                "relative flex items-center gap-3 px-4 py-3 transition-colors hover:bg-muted/40",
                isYou && "bg-primary/[0.06] dark:bg-primary/10"
              )}
            >
              {isYou ? (
                <span className="absolute inset-y-0 left-0 w-0.5 rounded-full bg-primary" aria-hidden />
              ) : null}

              <span
                className={cn(
                  "grid size-8 shrink-0 place-items-center rounded-full border font-mono text-sm font-semibold tabular-nums",
                  isTop
                    ? cn("border-transparent text-foreground", MEDALS[entry.rank - 1], "bg-foreground/5")
                    : "border-border text-muted-foreground"
                )}
              >
                {entry.rank}
              </span>

              <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-xs font-semibold text-primary">
                {initialsOf(entry.display_name ?? "A")}
              </span>

              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 truncate text-sm font-medium">
                  <Link href={`/portfolio/${entry.user_id}`} className="truncate hover:underline">
                    {entry.display_name ?? "Anonymous"}
                  </Link>
                  {isYou ? (
                    <span className="shrink-0 rounded-full bg-primary/15 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                      You
                    </span>
                  ) : null}
                </p>
                <div className="mt-1 h-1 w-full max-w-40 overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn(
                      "h-full rounded-full bg-gradient-to-r",
                      isTop ? "from-primary to-cyber-2" : "from-primary/50 to-cyber-2/40"
                    )}
                    style={{ width: `${Math.max(6, (entry.points / maxPoints) * 100)}%` }}
                  />
                </div>
              </div>

              <span className="hidden text-xs text-muted-foreground tabular-nums sm:block">
                {entry.solved_count} solved
              </span>
              <span className="w-16 text-right font-display text-sm font-semibold text-primary tabular-nums">
                {entry.points}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}