import Link from "next/link";
import { redirect } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Progress, ProgressLabel } from "@/components/ui/progress";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { LearningPathDetail } from "@/lib/paths/types";
import { STEP_STATUS_LABELS, pathProgress } from "@/lib/paths/types";

export const dynamic = "force-dynamic";

const STEP_VARIANT: Record<string, "default" | "secondary" | "outline"> = {
  completed: "default",
  unlocked: "secondary",
  locked: "outline",
};

export default async function PathDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "learning_path.view")) redirect("/dashboard");

  const { id } = await params;
  const result = await serverApiGet<LearningPathDetail>(`/paths/${id}`);
  if (!result.ok) redirect("/paths");
  const path = result.data;

  const progress = pathProgress(path);

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-3xl flex-1 p-6">
        <Link href="/paths" className="text-sm text-muted-foreground hover:text-foreground">
          ← All paths
        </Link>
        <h1 className="mt-3 text-2xl font-semibold">{path.title}</h1>
        <p className="mt-1 text-muted-foreground">
          {path.description ?? "Guided challenge sequence."}
        </p>

        <Card className="mt-6">
          <CardContent className="pt-6">
            <Progress value={progress} className="items-center gap-3">
              <ProgressLabel>
                {progress}% complete
              </ProgressLabel>
            </Progress>
          </CardContent>
        </Card>

        <ol className="mt-6 space-y-3">
          {path.steps.length === 0 ? (
            <p className="text-muted-foreground">This path has no steps yet.</p>
          ) : (
            path.steps.map((step) => (
              <li key={step.challenge_id}>
                <Card>
                  <CardContent className="flex items-center justify-between gap-4 pt-6">
                    <div className="flex items-center gap-3">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold tabular-nums">
                        {step.step_order}
                      </span>
                      <Link
                        href={`/challenges/${step.challenge_id}`}
                        className={
                          step.status === "locked"
                            ? "pointer-events-none text-muted-foreground"
                            : "font-medium hover:underline"
                        }
                      >
                        {step.title}
                      </Link>
                    </div>
                    <Badge variant={STEP_VARIANT[step.status] ?? "outline"}>
                      {STEP_STATUS_LABELS[step.status] ?? step.status}
                    </Badge>
                  </CardContent>
                </Card>
              </li>
            ))
          )}
        </ol>
      </main>
    </>
  );
}