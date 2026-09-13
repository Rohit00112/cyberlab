import { redirect } from "next/navigation";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { ChallengeForm } from "@/components/admin/challenge-form";
import { Button, buttonVariants } from "@/components/ui/button";
import { canServerUser, serverSessionUser } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export default async function NewChallengePage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "challenge.edit") && !canServerUser(user, "challenge.create")) {
    redirect("/dashboard");
  }

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-4xl flex-1 p-6">
        <div className="flex items-center gap-3">
          <Link href="/admin/challenges" className={buttonVariants({ variant: "outline", size: "sm" })}>
            ← Back
          </Link>
          <h1 className="text-2xl font-semibold">New challenge</h1>
        </div>
        <div className="mt-6">
          <ChallengeForm mode="create" />
        </div>
      </main>
    </>
  );
}