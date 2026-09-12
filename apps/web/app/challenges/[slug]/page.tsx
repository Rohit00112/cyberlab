import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import { ChallengeDetail } from "@/components/challenges/challenge-detail";
import { serverApiGet } from "@/lib/api-server";
import type { Challenge } from "@/lib/challenges/types";

export const dynamic = "force-dynamic";

export default async function ChallengeDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const result = await serverApiGet<Challenge[]>("/challenges");
  if (!result.ok) redirect("/auth/login");

  const challenge = result.data.find((c) => c.slug === slug);
  if (!challenge) notFound();

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <Link href="/challenges" className="text-sm text-muted-foreground hover:underline">
          ← Back to catalogue
        </Link>
        <div className="mt-4">
          <ChallengeDetail challenge={challenge} />
        </div>
      </main>
    </>
  );
}