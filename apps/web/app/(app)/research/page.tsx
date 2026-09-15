import Link from "next/link";
import { redirect } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import { Card, CardContent } from "@/components/ui/card";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { ResearchMetrics } from "@/lib/research/types";

export const dynamic = "force-dynamic";

export default async function ResearchHubPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "analytics.research")) redirect("/dashboard");

  const metricsResult = await serverApiGet<ResearchMetrics>("/research/metrics");
  const metrics = metricsResult.ok ? metricsResult.data : null;

  const links = [
    {
      href: "/research/insights",
      title: "Research insights",
      description: "Learning, engagement, challenge quality and recommendation metrics (§71).",
    },
    {
      href: "/research/graph",
      title: "Knowledge graph",
      description: "Skills, challenges and categories mapped from evidence (§72).",
    },
    {
      href: "/research/datasets",
      title: "Datasets",
      description: "Pseudonymized, expiring exports for offline analysis (§70).",
    },
    {
      href: "/research/experiments",
      title: "Experiments",
      description: "Registry of offline ML/GNN runs backed by exported data.",
    },
  ];

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div>
          <h1 className="text-2xl font-semibold">Research platform</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Pseudonymized data exports, dashboards and an experiment registry for the
            ML/GNN research track. Exports never contain real identities.
          </p>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Assessed students</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums">
                {metrics?.learning.assessed_users ?? "—"}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Weekly active users</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums">
                {metrics?.engagement.weekly_active_users ?? "—"}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Recommendations served</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums">
                {metrics?.recommendations.served ?? "—"}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <p className="text-sm text-muted-foreground">Completion rate</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums">
                {metrics
                  ? `${(metrics.learning.completion_rate * 100).toFixed(0)}%`
                  : "—"}
              </p>
            </CardContent>
          </Card>
        </div>

        <section className="mt-8">
          <h2 className="text-lg font-semibold">Research tools</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {links.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="rounded-lg border p-4 transition-colors hover:bg-muted"
              >
                <h3 className="font-medium">{link.title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{link.description}</p>
              </Link>
            ))}
          </div>
        </section>
      </main>
    </>
  );
}