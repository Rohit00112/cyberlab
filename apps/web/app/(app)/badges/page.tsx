"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { Badge as UiBadge } from "@/components/ui/badge";
import { BadgeIcon } from "@/components/badges/badge-icon";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { useAuth } from "@/components/providers/auth-provider";
import type { Badge, BadgeEarned } from "@/lib/badges/types";

export default function BadgesCataloguePage() {
  const { user } = useAuth();
  const [allBadges, setAllBadges] = useState<Badge[]>([]);
  const [earnedBadges, setEarnedBadges] = useState<BadgeEarned[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "earned" | "locked">("all");

  useEffect(() => {
    let mounted = true;
    Promise.all([
      api.get<Badge[]>("/badges").catch(() => []),
      user ? api.get<BadgeEarned[]>("/badges/me").catch(() => []) : Promise.resolve([]),
    ]).then(([catalogue, earned]) => {
      if (mounted) {
        setAllBadges(catalogue);
        setEarnedBadges(earned);
        setLoading(false);
      }
    });

    return () => {
      mounted = false;
    };
  }, [user]);

  const earnedMap = useMemo(() => {
    const map = new Map<string, BadgeEarned>();
    for (const eb of earnedBadges) {
      map.set(eb.code, eb);
    }
    return map;
  }, [earnedBadges]);

  const filteredBadges = useMemo(() => {
    return allBadges.filter((b) => {
      const isEarned = earnedMap.has(b.code);
      if (filter === "earned" && !isEarned) return false;
      if (filter === "locked" && isEarned) return false;
      if (search.trim()) {
        const q = search.toLowerCase();
        const matchName = b.name.toLowerCase().includes(q);
        const matchDesc = (b.description ?? "").toLowerCase().includes(q);
        const matchSkill = (b.skill_name ?? "").toLowerCase().includes(q);
        if (!matchName && !matchDesc && !matchSkill) return false;
      }
      return true;
    });
  }, [allBadges, earnedMap, filter, search]);

  const totalEarned = earnedBadges.length;
  const totalBadges = allBadges.length;
  const progressPercent = totalBadges > 0 ? Math.round((totalEarned / totalBadges) * 100) : 0;

  return (
    <>
            <div className="contents">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Achievements & Badges</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Earn skill badges and proof-of-competency by solving challenges and winning competitions.
            </p>
          </div>
          {user ? (
            <div className="flex items-center gap-3">
              <Link href="/profile">
                <Button variant="outline" size="sm">
                  View in profile
                </Button>
              </Link>
            </div>
          ) : null}
        </div>

        {user ? (
          <div className="mt-6 rounded-lg border bg-card p-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium">Your Badge Progress</p>
                <p className="text-2xl font-bold tabular-nums">
                  {totalEarned} <span className="text-sm font-normal text-muted-foreground">/ {totalBadges} unlocked</span>
                </p>
              </div>
              <div className="w-full sm:w-64">
                <div className="flex justify-between text-xs text-muted-foreground mb-1">
                  <span>Progress</span>
                  <span>{progressPercent}%</span>
                </div>
                <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-500 rounded-full"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant={filter === "all" ? "default" : "outline"}
              onClick={() => setFilter("all")}
            >
              All ({allBadges.length})
            </Button>
            {user ? (
              <>
                <Button
                  size="sm"
                  variant={filter === "earned" ? "default" : "outline"}
                  onClick={() => setFilter("earned")}
                >
                  Unlocked ({totalEarned})
                </Button>
                <Button
                  size="sm"
                  variant={filter === "locked" ? "default" : "outline"}
                  onClick={() => setFilter("locked")}
                >
                  Locked ({totalBadges - totalEarned})
                </Button>
              </>
            ) : null}
          </div>

          <div className="w-full sm:w-72">
            <Input
              placeholder="Search badges by title or skill..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-9 text-xs"
            />
          </div>
        </div>

        {loading ? (
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="h-44 rounded-lg border bg-card/40 animate-pulse" />
            ))}
          </div>
        ) : filteredBadges.length === 0 ? (
          <div className="mt-8 rounded-lg border p-12 text-center text-muted-foreground">
            No badges match your criteria.
          </div>
        ) : (
          <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filteredBadges.map((badge) => {
              const earned = earnedMap.get(badge.code);
              const isUnlocked = Boolean(earned);

              return (
                <Card
                  key={badge.id}
                  className={`relative flex flex-col justify-between overflow-hidden transition-all duration-200 ${
                    isUnlocked
                      ? "border-primary/40 bg-gradient-to-br from-primary/5 via-card to-background shadow-sm"
                      : "opacity-80 hover:opacity-100"
                  }`}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-3">
                        <div
                          className={`flex h-12 w-12 items-center justify-center rounded-xl text-2xl shadow-inner ${
                            isUnlocked
                              ? "bg-primary/20 ring-2 ring-primary/40"
                              : "bg-muted text-muted-foreground grayscale"
                          }`}
                        >
                          <BadgeIcon badge={badge} className="size-6" />
                        </div>
                        <div>
                          <CardTitle className="text-base font-semibold leading-tight">
                            {badge.name}
                          </CardTitle>
                          {badge.skill_name ? (
                            <span className="mt-0.5 inline-block text-xs text-muted-foreground">
                              {badge.skill_name}
                            </span>
                          ) : null}
                        </div>
                      </div>
                      <UiBadge
                        variant={isUnlocked ? "default" : "outline"}
                        className="text-[10px] shrink-0"
                      >
                        {isUnlocked ? "Unlocked" : "Locked"}
                      </UiBadge>
                    </div>
                  </CardHeader>

                  <CardContent className="pt-2 text-xs text-muted-foreground flex-1 flex flex-col justify-between">
                    <p className="line-clamp-3 leading-relaxed">
                      {badge.description ?? "Complete cybersecurity challenges to unlock this badge."}
                    </p>

                    <div className="mt-4 pt-3 border-t border-border/60 flex items-center justify-between text-[11px]">
                      {isUnlocked && earned ? (
                        <span className="text-primary font-medium">
                          Unlocked on {new Date(earned.earned_at).toLocaleDateString()}
                        </span>
                      ) : (
                        <span className="font-mono text-muted-foreground">
                          Requirement: {String((badge.criteria as Record<string, unknown>)?.code ?? badge.code)}
                        </span>
                      )}
                      <span className="font-mono text-muted-foreground/60 text-[10px]">
                        #{badge.code}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
