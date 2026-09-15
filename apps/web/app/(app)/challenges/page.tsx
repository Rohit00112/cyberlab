import { redirect } from "next/navigation";

import { ChallengeCatalogue } from "@/components/challenges/challenge-catalogue";
import { serverApiGet } from "@/lib/api-server";
import type { Challenge } from "@/lib/challenges/types";

export const dynamic = "force-dynamic";

export default async function ChallengesPage() {
  const result = await serverApiGet<Challenge[]>("/challenges");
  if (!result.ok) redirect("/auth/login");

  return (
    <>
            <div className="contents">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold">Challenge Catalogue</h1>
          <p className="mt-1 text-muted-foreground">
            Pick a challenge, work through it, and earn points.
          </p>
        </div>
        <ChallengeCatalogue challenges={result.data} />
      </div>
    </>
  );
}