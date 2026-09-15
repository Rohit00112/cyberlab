"use client";

import Link from "next/link";
import { ShieldHalfIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export function AppLogo({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <Link
      href="/dashboard"
      className={cn("group flex items-center gap-2", className)}
      aria-label="IIC CyberLab home"
    >
      <span className="relative grid size-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-cyber to-cyber-2 text-primary-foreground shadow-[0_0_16px_-4px_var(--cyber)] transition-transform group-hover:scale-105">
        <ShieldHalfIcon className="size-4.5" />
        <span className="absolute inset-0 rounded-lg ring-1 ring-inset ring-white/25" />
      </span>
      {!compact ? (
        <span className="text-sm font-semibold tracking-tight">
          IIC <span className="text-cyber-gradient">CyberLab</span>
        </span>
      ) : null}
    </Link>
  );
}