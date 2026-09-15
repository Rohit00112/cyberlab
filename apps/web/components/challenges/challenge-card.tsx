import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  difficultyLabel,
  type Challenge,
  type Difficulty,
} from "@/lib/challenges/types";
import { cn } from "@/lib/utils";
import { ChevronRightIcon, TimerIcon } from "lucide-react";

const DIFFICULTY_STYLES: Record<Difficulty, { badge: string; bar: string; label: string }> = {
  beginner: { badge: "text-success bg-success/10", bar: "from-success to-teal-400", label: "text-success" },
  intermediate: { badge: "text-warning bg-warning/10", bar: "from-warning to-amber-400", label: "text-warning" },
  advanced: { badge: "text-destructive bg-destructive/10", bar: "from-destructive to-rose-400", label: "text-destructive" },
};

export function ChallengeCard({ challenge }: { challenge: Challenge }) {
  const style = DIFFICULTY_STYLES[challenge.difficulty];

  return (
    <Link href={`/challenges/${challenge.slug}`} className="group focus:outline-none">
      <Card interactive className="relative h-full">
        <div
          aria-hidden
          className={cn(
            "absolute inset-x-0 top-0 h-1 bg-gradient-to-r opacity-70 transition-opacity group-hover:opacity-100",
            style.bar
          )}
        />
        <CardContent className="relative flex h-full flex-col gap-3 pt-5">
          <div className="flex items-start justify-between gap-3">
            <Badge variant="secondary" className="font-medium">
              {challenge.category}
            </Badge>
            <span className="inline-flex items-center gap-1 rounded-md border border-primary/20 bg-primary/5 px-2 py-0.5 text-sm font-semibold text-primary tabular-nums">
              {challenge.points}
              <span className="text-xs font-normal text-muted-foreground">pts</span>
            </span>
          </div>

          <div>
            <h3 className="font-display text-base font-semibold leading-snug transition-colors group-hover:text-primary">
              {challenge.title}
            </h3>
            <p className="mt-1.5 line-clamp-2 text-sm text-muted-foreground">
              {challenge.description}
            </p>
          </div>

          <div className="mt-auto flex items-center gap-3 pt-2">
            <span className={cn("text-xs font-medium", style.label)}>{difficultyLabel(challenge.difficulty)}</span>
            <span className="mx-0.5 h-3 w-px bg-border" aria-hidden />
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <TimerIcon className="size-3" />
              {challenge.estimated_minutes ? `~${challenge.estimated_minutes} min` : "self-paced"}
            </span>
            <span className="ml-auto inline-flex items-center gap-0.5 text-sm font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
              Solve
              <ChevronRightIcon className="size-4" />
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}