import Link from "next/link";
import { redirect } from "next/navigation";

import { PathForm } from "@/components/admin/path-form";
import { PathStepForm } from "@/components/admin/path-step-form";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { Challenge } from "@/lib/challenges/types";
import type { LearningPathSummary } from "@/lib/paths/types";

export const dynamic = "force-dynamic";

export default async function AdminPathsPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "learning_path.manage")) redirect("/dashboard");

  const [pathsResult, challengesResult] = await Promise.all([
    serverApiGet<LearningPathSummary[]>("/admin/paths"),
    serverApiGet<Challenge[]>("/challenges?limit=200"),
  ]);
  if (!pathsResult.ok || !challengesResult.ok) redirect("/auth/login");
  const paths = pathsResult.data;
  const challenges = challengesResult.data;

  return (
    <>
            <div className="contents">
        <div>
          <h1 className="text-2xl font-semibold">Learning path management</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Create ordered challenge sequences and publish them to students.
          </p>
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Create a path</CardTitle>
            </CardHeader>
            <CardContent>
              <PathForm />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Add a step</CardTitle>
            </CardHeader>
            <CardContent>
              <PathStepForm paths={paths} challenges={challenges} />
            </CardContent>
          </Card>
        </div>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-base">All paths</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {paths.length === 0 ? (
              <p className="text-muted-foreground">No paths yet — create the first one.</p>
            ) : (
              <ul className="divide-y rounded-lg border">
                {paths.map((path) => (
                  <li key={path.id} className="flex items-center justify-between gap-4 p-4">
                    <div>
                      <Link href={`/paths/${path.id}`} className="font-medium hover:underline">
                        {path.title}
                      </Link>
                      <p className="text-sm text-muted-foreground">
                        {path.slug}
                        {path.description ? ` — ${path.description}` : ""}
                      </p>
                    </div>
                    <Badge variant={path.is_published ? "default" : "secondary"}>
                      {path.is_published ? "Published" : "Draft"}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}