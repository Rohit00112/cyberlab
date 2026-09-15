"use client";

import Link from "next/link";

import { CompetitionCountdown } from "@/components/competitions/countdown";
import { CompetitionStatusBadge } from "@/components/competitions/competition-status-badge";
import { Card } from "@/components/ui/card";
import type { CompetitionSummary } from "@/lib/competitions/types";
import { ChevronRightIcon, ListChecksIcon, UsersIcon } from "lucide-react";

export function CompetitionCard({ competition }: { competition: CompetitionSummary }) {
  return (
    <Link href={`/competitions/${competition.id}`} className="group focus:outline-none">
      <Card interactive className="relative h-full p-5">
        <div className="flex items-start justify-between gap-3">
          <CompetitionStatusBadge status={competition.status} />
          <ChevronRightIcon className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
        </div>

        <h3 className="mt-3 font-display text-lg font-semibold leading-snug transition-colors group-hover:text-primary">
          {competition.title}
        </h3>
        <p className="mt-1.5 line-clamp-2 text-sm text-muted-foreground">
          {competition.description ?? "No description provided."}
        </p>

        <div className="mt-4 flex items-center gap-4 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <ListChecksIcon className="size-4" />
            {competition.challenge_count} challenges
          </span>
          <span className="inline-flex items-center gap-1.5">
            <UsersIcon className="size-4" />
            {competition.participant_count} players
          </span>
        </div>

        <div className="mt-4 border-t border-border/70 pt-3">
          <CompetitionCountdown
            status={competition.status}
            startAt={competition.start_at}
            endAt={competition.end_at}
          />
        </div>
      </Card>
    </Link>
  );
}