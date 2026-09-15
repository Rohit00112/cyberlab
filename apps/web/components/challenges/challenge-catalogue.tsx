"use client";

import { useMemo, useState } from "react";

import { ChallengeCard } from "@/components/challenges/challenge-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  type Challenge,
  type Difficulty,
} from "@/lib/challenges/types";
import { cn } from "@/lib/utils";
import { SearchIcon, XIcon } from "lucide-react";

const CATEGORY_ORDER = [
  "Linux",
  "Networking",
  "Web Security",
  "Cryptography",
  "Digital Forensics",
  "OSINT",
  "System Security",
  "Blue Team",
  "Secure Coding",
  "Cloud Security",
];

const DIFFICULTY_ORDER: { value: Difficulty; label: string }[] = [
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
];

export function ChallengeCatalogue({ challenges }: { challenges: Challenge[] }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("all");
  const [difficulty, setDifficulty] = useState<string>("all");

  const categories = useMemo(() => {
    const present = new Set(challenges.map((c) => c.category));
    return CATEGORY_ORDER.filter((c) => present.has(c));
  }, [challenges]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return challenges.filter((c) => {
      if (q && !`${c.title} ${c.description} ${c.skills.join(" ")}`.toLowerCase().includes(q)) {
        return false;
      }
      if (category !== "all" && c.category !== category) return false;
      if (difficulty !== "all" && c.difficulty !== (difficulty as Difficulty)) return false;
      return true;
    });
  }, [challenges, query, category, difficulty]);

  const hasFilters = query !== "" || category !== "all" || difficulty !== "all";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search challenges…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-64 pl-8"
            aria-label="Search challenges"
          />
        </div>
        <Select value={category} onValueChange={(value) => setCategory(value ?? "all")}>
          <SelectTrigger className="w-44" aria-label="Filter by category">
            <SelectValue placeholder="All categories" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All categories</SelectItem>
            {categories.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <div className="flex items-center gap-1 rounded-lg border border-border bg-card p-1">
          {DIFFICULTY_ORDER.map((option) => (
            <button
              key={option.value}
              onClick={() => setDifficulty(difficulty === option.value ? "all" : option.value)}
              className={cn(
                "rounded-md px-2.5 py-1 text-sm font-medium transition-colors",
                difficulty === option.value
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {option.label}
            </button>
          ))}
        </div>

        <span className="ml-auto text-sm text-muted-foreground tabular-nums">
          {filtered.length} / {challenges.length}
        </span>
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-16 text-center">
          <p className="text-sm font-medium">No challenges match your filters</p>
          <p className="mt-1 text-sm text-muted-foreground">Try a different search or clear the filters.</p>
          {hasFilters ? (
            <Button
              variant="outline"
              size="sm"
              className="mt-4"
              onClick={() => {
                setQuery("");
                setCategory("all");
                setDifficulty("all");
              }}
            >
              <XIcon />
              Clear filters
            </Button>
          ) : null}
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((challenge) => (
            <ChallengeCard key={challenge.id} challenge={challenge} />
          ))}
        </div>
      )}
    </div>
  );
}