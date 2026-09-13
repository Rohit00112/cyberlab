import { redirect } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import { LabStatusFilter } from "@/components/admin/lab-status-filter";
import { TerminateLab } from "@/components/admin/terminate-lab";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import {
  LAB_STATUS_LABELS,
  type LabHealth,
  type LabList,
} from "@/lib/challenges/types";

export const dynamic = "force-dynamic";

export default async function AdminLabsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "lab.admin")) redirect("/dashboard");

  const { status } = await searchParams;
  const path = `/admin/labs?limit=100${status ? `&status=${encodeURIComponent(status)}` : ""}`;
  const result = await serverApiGet<LabList>(path);
  if (!result.ok) redirect("/auth/login");
  const { items: labs, total } = result.data;

  const healthResult = await serverApiGet<LabHealth>("/health/lab");
  const health = healthResult.ok ? healthResult.data : null;

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Lab monitoring</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Live lab instances across all users. Terminating force-stops the
              container and marks the lab expired.
            </p>
          </div>
          <LabStatusFilter />
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
          <Badge variant={health && health.docker.reachable ? "default" : "destructive"}>
            Docker {health && health.docker.reachable ? "reachable" : "unreachable"}
          </Badge>
          <Badge variant="secondary">
            Running: {health?.labs.running ?? "—"}
          </Badge>
          <Badge variant="secondary">
            Provisioning: {health?.labs.provisioning ?? "—"}
          </Badge>
          <Badge variant="secondary">Total labs: {total}</Badge>
        </div>

        <div className="mt-6">
          {labs.length === 0 ? (
            <p className="text-muted-foreground">No labs match this view.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Challenge</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead>Container / error</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {labs.map((lab) => (
                  <TableRow key={lab.id}>
                    <TableCell>
                      <p className="font-medium">{lab.user_display_name ?? "—"}</p>
                      <p className="text-xs text-muted-foreground">{lab.user_email}</p>
                    </TableCell>
                    <TableCell>
                      {lab.challenge_title ?? lab.challenge_slug ?? "—"}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          lab.status === "error"
                            ? "destructive"
                            : lab.status === "running"
                              ? "default"
                              : "secondary"
                        }
                      >
                        {LAB_STATUS_LABELS[lab.status] ?? lab.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground tabular-nums">
                      {lab.expires_at
                        ? new Date(lab.expires_at).toLocaleString()
                        : "—"}
                    </TableCell>
                    <TableCell className="max-w-64 font-mono text-xs text-muted-foreground truncate">
                      {lab.error_message ?? lab.container_name ?? "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      {lab.status === "running" || lab.status === "provisioning" ? (
                        <TerminateLab lab={lab} />
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </main>
    </>
  );
}