import { redirect } from "next/navigation";

import { CompetitionForm } from "@/components/admin/competition-form";
import { canServerUser, serverSessionUser } from "@/lib/api-server";

export const dynamic = "force-dynamic";

export default async function NewCompetitionPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "competition.manage")) redirect("/dashboard");

  return (
    <>
            <div className="contents">
        <h1 className="text-2xl font-semibold">New competition</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Created in draft. Open registration when it&apos;s ready.
        </p>
        <div className="mt-6 rounded-lg border p-4">
          <CompetitionForm mode="create" />
        </div>
      </div>
    </>
  );
}