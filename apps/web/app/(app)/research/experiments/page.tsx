import { redirect } from "next/navigation";

import { ExperimentActions } from "@/components/research/experiment-actions";
import { ExperimentForm } from "@/components/research/experiment-form";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { ResearchExperiment } from "@/lib/research/types";

export const dynamic = "force-dynamic";

function describeValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default async function ResearchExperimentsPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "analytics.research")) redirect("/dashboard");

  const result = await serverApiGet<ResearchExperiment[]>("/research/experiments");
  if (!result.ok) redirect("/auth/login");
  const experiments = result.data;

  return (
    <>
            <div className="contents">
        <div>
          <h1 className="text-2xl font-semibold">ML experiment registry</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            A ledger for offline GNN/ML runs (PRD §72). The API never executes
            models — record a run, then use the linked research scripts against
            exported datasets.
          </p>
        </div>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-lg">Register an experiment</CardTitle>
          </CardHeader>
          <CardContent>
            <ExperimentForm />
          </CardContent>
        </Card>

        <section className="mt-8">
          <h2 className="text-lg font-semibold">Runs</h2>
          <div className="mt-3">
            {experiments.length === 0 ? (
              <p className="text-muted-foreground">No experiments registered yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Metrics</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {experiments.map((experiment) => (
                    <TableRow key={experiment.id}>
                      <TableCell className="font-medium">{experiment.name}</TableCell>
                      <TableCell>{experiment.model_ref}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{experiment.status}</Badge>
                      </TableCell>
                      <TableCell className="max-w-64 truncate text-muted-foreground">
                        {describeValue(experiment.metrics)}
                      </TableCell>
                      <TableCell className="text-muted-foreground tabular-nums">
                        {new Date(experiment.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell className="text-right">
                        <ExperimentActions id={experiment.id} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </section>
      </div>
    </>
  );
}