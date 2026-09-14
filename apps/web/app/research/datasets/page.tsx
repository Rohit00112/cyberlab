import { redirect } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import { DatasetActions } from "@/components/research/dataset-actions";
import { DatasetForm } from "@/components/research/dataset-form";
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
import type { ResearchDataset } from "@/lib/research/types";

export const dynamic = "force-dynamic";

export default async function ResearchDatasetsPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "analytics.research")) redirect("/dashboard");

  const result = await serverApiGet<ResearchDataset[]>("/research/datasets");
  if (!result.ok) redirect("/auth/login");
  const datasets = result.data;

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div>
          <h1 className="text-2xl font-semibold">Research datasets</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Pseudonymized exports for offline analysis (PRD §70). Identities are
            HMAC-derived ids only; raw PII never leaves the API.
          </p>
        </div>

        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-lg">Build a new export</CardTitle>
          </CardHeader>
          <CardContent>
            <DatasetForm />
          </CardContent>
        </Card>

        <section className="mt-8">
          <h2 className="text-lg font-semibold">Exports</h2>
          <div className="mt-3">
            {datasets.length === 0 ? (
              <p className="text-muted-foreground">No datasets built yet.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Kind</TableHead>
                    <TableHead className="text-right">Rows</TableHead>
                    <TableHead>Expires</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {datasets.map((dataset) => {
                    const expired =
                      dataset.expires_at !== null &&
                      dataset.expires_at !== undefined &&
                      new Date(dataset.expires_at) < new Date();
                    return (
                      <TableRow key={dataset.id}>
                        <TableCell className="font-medium">{dataset.name}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{dataset.kind}</Badge>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">
                          {dataset.row_count}
                        </TableCell>
                        <TableCell>
                          {expired ? (
                            <span className="text-destructive">Expired</span>
                          ) : dataset.expires_at ? (
                            new Date(dataset.expires_at).toLocaleDateString()
                          ) : (
                            "—"
                          )}
                        </TableCell>
                        <TableCell className="text-muted-foreground tabular-nums">
                          {new Date(dataset.created_at).toLocaleDateString()}
                        </TableCell>
                        <TableCell>
                          {expired ? null : (
                            <DatasetActions id={dataset.id} name={dataset.name} />
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </div>
        </section>
      </main>
    </>
  );
}