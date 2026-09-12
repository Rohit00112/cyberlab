"use client";

import { useMemo, useState } from "react";

import { ChallengeCard } from "@/components/challenges/challenge-card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DIFFICULTY_LABELS,
  type Challenge,
  type Difficulty,
} from "@/lib/challenges/types";

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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Input
          placeholder="Search challenges…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="max-w-xs"
          aria-label="Search challenges"
        />
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
        <Select value={difficulty} onValueChange={(value) => setDifficulty(value ?? "all")}>
          <SelectTrigger className="w-40" aria-label="Filter by difficulty">
            <SelectValue placeholder="All difficulties" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All difficulties</SelectItem>
            {Object.entries(DIFFICULTY_LABELS).map(([value, label]) => (
              <SelectItem key={value} value={value}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="ml-auto text-sm text-muted-foreground">
          {filtered.length} / {challenges.length}
        </span>
      </div>

      {filtered.length === 0 ? (
        <p className="py-12 text-center text-muted-foreground">
          No challenges match your filters.
        </p>
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