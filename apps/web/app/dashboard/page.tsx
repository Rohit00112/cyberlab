"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { RequireAuth } from "@/components/providers/require-auth";
import { useAuth } from "@/components/providers/auth-provider";
import { hasPermission } from "@/lib/auth/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { RecommendationCard } from "@/components/challenges/recommendation-card";
import type {
  ChallengeRecommendation,
  Lab,
  UserProfile,
  UserStats,
} from "@/lib/challenges/types";
import { LAB_STATUS_LABELS } from "@/lib/challenges/types";

function StatCard({
  label,
  value,
  suffix,
}: {
  label: string;
  value: number | null;
  suffix?: string;
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="mt-1 text-3xl font-semibold tabular-nums">
          {value === null ? "—" : `${value}${suffix ?? ""}`}
        </p>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<UserStats | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [labs, setLabs] = useState<Lab[] | null>(null);
  const [recommendations, setRecommendations] = useState<ChallengeRecommendation[]>([]);

  useEffect(() => {
    api
      .get<UserStats>("/submissions/stats")
      .then(setStats)
      .catch(() => setStats(null));
    api
      .get<UserProfile>("/users/me")
      .then(setProfile)
      .catch(() => setProfile(null));
    if (hasPermission("lab.launch")) {
      api
        .get<Lab[]>("/labs")
        .then(setLabs)
        .catch(() => setLabs(null));
    }
    api
      .get<ChallengeRecommendation[]>("/recommendations/challenges?limit=6")
      .then(setRecommendations)
      .catch(() => setRecommendations([]));
  }, []);

  const activeLabs = labs?.filter(
    (lab) => lab.status === "running" || lab.status === "provisioning",
  );
  const skills = Array.from(
    new Set((profile?.recent_solves ?? []).flatMap((solve) => solve.skills)),
  ).slice(0, 12);

  return (
    <RequireAuth>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <h1 className="text-2xl font-semibold">
          Welcome, {user?.display_name ?? "student"}
        </h1>
        <p className="mt-2 text-muted-foreground">
          Browse the catalogue to start working on challenges.
        </p>
        <div className="mt-6 grid gap-4 sm:grid-cols-3">
          <StatCard label="Points" value={stats?.points ?? null} />
          <StatCard label="Solved" value={stats?.solved_count ?? null} />
          <StatCard label="Attempts" value={stats?.attempts ?? null} />
        </div>

        {activeLabs && activeLabs.length > 0 ? (
          <Card className="mt-6">
            <CardContent className="pt-6">
              <h2 className="font-semibold">Active labs</h2>
              <ul className="mt-3 divide-y">
                {activeLabs.slice(0, 5).map((lab) => (
                  <li key={lab.id} className="flex items-center justify-between py-2">
                    <div>
                      <p className="font-medium">
                        {lab.challenge_title ?? lab.challenge_slug}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {LAB_STATUS_LABELS[lab.status]}
                        {lab.expires_at ? ` · expires ${new Date(lab.expires_at).toLocaleTimeString()}` : ""}
                      </p>
                    </div>
                    <Link href="/labs" className="text-sm underline">
                      Manage
                    </Link>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        ) : null}

        {profile && profile.recent_solves.length > 0 ? (
          <Card className="mt-6">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <h2 className="font-semibold">Your skills</h2>
                <Link href="/profile" className="text-sm underline">
                  Full profile
                </Link>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {skills.map((skill) => (
                  <Badge key={skill} variant="outline">
                    {skill}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        ) : null}

        {recommendations.length > 0 ? (
          <div className="mt-6">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold">Recommended for you</h2>
              <Link href="/challenges" className="text-sm underline">
                Browse all
              </Link>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {recommendations.map((rec) => (
                <RecommendationCard key={rec.challenge_id} recommendation={rec} />
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-6 flex gap-3">
          <Link href="/challenges">
            <Button>Browse challenges</Button>
          </Link>
          <Link href="/leaderboard">
            <Button variant="outline">View leaderboard</Button>
          </Link>
          <Link href="/profile">
            <Button variant="outline">My profile</Button>
          </Link>
        </div>
      </main>
    </RequireAuth>
  );
}