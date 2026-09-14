"use client";

import { useEffect, useState } from "react";
import type { CompetitionStatus } from "@/lib/competitions/types";

interface Props {
  status: CompetitionStatus;
  startAt?: string | null;
  endAt?: string | null;
}

function formatTimeRemaining(targetDate: Date, nowTs: number) {
  const diff = targetDate.getTime() - nowTs;
  if (diff <= 0) return null;

  const seconds = Math.floor((diff / 1000) % 60);
  const minutes = Math.floor((diff / 1000 / 60) % 60);
  const hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));

  return { days, hours, minutes, seconds };
}

export function CompetitionCountdown({ status, startAt, endAt }: Props) {
  const [nowTs, setNowTs] = useState(() => Date.now());

  useEffect(() => {
    const interval = setInterval(() => {
      setNowTs(Date.now());
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  let targetDate: Date | null = null;
  let label = "";
  let isLive = false;

  if (status === "scheduled" && startAt) {
    targetDate = new Date(startAt);
    label = "Starts in";
  } else if (status === "live" && endAt) {
    targetDate = new Date(endAt);
    label = "Ends in";
    isLive = true;
  }

  if (!targetDate) {
    if (status === "live") {
      return (
        <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-2 text-sm text-emerald-400">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
          </span>
          <span>Competition is live!</span>
        </div>
      );
    }
    return null;
  }

  const remaining = formatTimeRemaining(targetDate, nowTs);

  if (!remaining) {
    return (
      <div className="text-sm text-muted-foreground">
        {status === "scheduled" ? "Starting momentarily..." : "Competition ended"}
      </div>
    );
  }

  return (
    <div
      className={`flex items-center gap-3 rounded-lg border px-4 py-2.5 text-sm ${
        isLive
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
          : "border-blue-500/30 bg-blue-500/10 text-blue-300"
      }`}
    >
      {isLive ? (
        <span className="relative flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500"></span>
        </span>
      ) : null}
      <span className="font-medium text-foreground">{label}:</span>
      <div className="flex items-center gap-2 font-mono tabular-nums">
        {remaining.days > 0 ? (
          <span>
            <strong className="text-foreground">{remaining.days}</strong>d
          </span>
        ) : null}
        <span>
          <strong className="text-foreground">
            {String(remaining.hours).padStart(2, "0")}
          </strong>
          h
        </span>
        <span>
          <strong className="text-foreground">
            {String(remaining.minutes).padStart(2, "0")}
          </strong>
          m
        </span>
        <span>
          <strong className="text-foreground">
            {String(remaining.seconds).padStart(2, "0")}
          </strong>
          s
        </span>
      </div>
    </div>
  );
}
