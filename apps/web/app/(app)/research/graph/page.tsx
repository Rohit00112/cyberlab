import { redirect } from "next/navigation";

import { GraphView } from "@/components/research/graph-view";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { ResearchGraph } from "@/lib/research/types";

export const dynamic = "force-dynamic";

export default async function ResearchGraphPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "analytics.research")) redirect("/dashboard");

  const result = await serverApiGet<ResearchGraph>("/research/graph");
  if (!result.ok) redirect("/auth/login");
  const graph = result.data;

  return (
    <>
            <div className="contents">
        <div>
          <h1 className="text-2xl font-semibold">Knowledge graph</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Challenges linked to skills and categories, learning-path order, and
            co-solved relationships inferred from submissions (PRD §72).
          </p>
        </div>
        <div className="mt-6">
          <GraphView graph={graph} />
        </div>
      </div>
    </>
  );
}