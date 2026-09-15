import { redirect } from "next/navigation";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { AuditFilter } from "@/components/admin/audit-filter";
import { buttonVariants } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { AuditLog } from "@/lib/challenges/types";

export const dynamic = "force-dynamic";

export default async function AdminAuditPage({
  searchParams,
}: {
  searchParams: Promise<{ event?: string }>;
}) {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "audit.view")) redirect("/dashboard");

  const { event } = await searchParams;
  const path = `/audit/logs?limit=100${event ? `&event=${encodeURIComponent(event)}` : ""}`;
  const result = await serverApiGet<AuditLog[]>(path);
  if (!result.ok) redirect("/auth/login");
  const logs = result.data;

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Audit log</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Append-only record of security-relevant events.
            </p>
          </div>
          <AuditFilter />
        </div>

        <div className="mt-6">
          {logs.length === 0 ? (
            <p className="text-muted-foreground">No events recorded yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Event</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead className="text-right">Target</TableHead>
                  <TableHead>IP</TableHead>
                  <TableHead className="text-right">When</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.map((log) => (
                  <TableRow key={log.id}>
                    <TableCell className="font-mono text-xs">{log.event}</TableCell>
                    <TableCell className="font-medium">
                      {log.display_name ?? log.user_id ?? "system"}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground font-mono text-xs">
                      {log.target_id ?? "—"}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {log.ip_address ?? "—"}
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground tabular-nums">
                      {new Date(log.created_at).toLocaleString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        <p className="mt-6 text-sm text-muted-foreground">
          Want deeper forensics? Open{" "}
          <Link
            href={`${process.env.NEXT_PUBLIC_API_BASE?.replace(/\/api\/v1$/, "") ?? "http://localhost:8000"}/docs`}
            target="_blank"
            className={buttonVariants({ variant: "link", size: "sm" })}
          >
            API docs
          </Link>{" "}
          (raw rows include details).
        </p>
      </main>
    </>
  );
}