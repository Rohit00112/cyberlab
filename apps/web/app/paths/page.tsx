import Link from "next/link";
import { redirect } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { LearningPathSummary } from "@/lib/paths/types";

export const dynamic = "force-dynamic";

export default async function PathsPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "learning_path.view")) redirect("/dashboard");

  const result = await serverApiGet<LearningPathSummary[]>("/paths");
  if (!result.ok) redirect("/auth/login");
  const paths = result.data;

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div>
          <h1 className="text-2xl font-semibold">Learning paths</h1>
          <p className="mt-1 text-muted-foreground">
            Curated challenge sequences that build up a skill step by step.
          </p>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {paths.length === 0 ? (
            <p className="text-muted-foreground">
              No learning paths published yet.
            </p>
          ) : (
            paths.map((path) => (
              <Link key={path.id} href={`/paths/${path.id}`} className="group focus:outline-none">
                <Card className="h-full transition-colors group-hover:ring-primary group-focus-visible:ring-2 group-focus-visible:ring-primary">
                  <CardHeader>
                    <div className="flex items-start justify-between gap-2">
                      <CardTitle>{path.title}</CardTitle>
                      <Badge variant="outline">Path</Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="line-clamp-2 text-sm text-muted-foreground">
                      {path.description ?? "A guided challenge sequence."}
                    </p>
                  </CardContent>
                </Card>
              </Link>
            ))
          )}
        </div>
      </main>
    </>
  );
}