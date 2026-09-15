import { notFound, redirect } from "next/navigation";
import Link from "next/link";

import { ChallengeForm } from "@/components/admin/challenge-form";
import { buttonVariants } from "@/components/ui/button";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { Challenge } from "@/lib/challenges/types";

export const dynamic = "force-dynamic";

export default async function EditChallengePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "challenge.edit")) redirect("/dashboard");

  const { id } = await params;
  const result = await serverApiGet<Challenge>(`/challenges/${id}`);
  if (!result.ok) {
    if (result.status === 404) notFound();
    redirect("/auth/login");
  }
  const challenge = result.data;

  return (
    <>
            <div className="contents">
        <div className="flex items-center gap-3">
          <Link href="/admin/challenges" className={buttonVariants({ variant: "outline", size: "sm" })}>
            ← Back
          </Link>
          <h1 className="text-2xl font-semibold">Edit challenge</h1>
        </div>
        <div className="mt-6">
          <ChallengeForm mode="edit" initial={challenge} />
        </div>
      </div>
    </>
  );
}