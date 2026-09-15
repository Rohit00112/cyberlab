import { redirect } from "next/navigation";

import { UserToggle } from "@/components/admin/user-toggle";
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
import type { AdminUser } from "@/lib/challenges/types";

export const dynamic = "force-dynamic";

export default async function AdminUsersPage({
  searchParams,
}: {
  searchParams: Promise<{ role?: string }>;
}) {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "user.view")) redirect("/dashboard");

  const { role } = await searchParams;
  const path = `/users?limit=200${role ? `&role=${encodeURIComponent(role)}` : ""}`;
  const result = await serverApiGet<AdminUser[]>(path);
  if (!result.ok) redirect("/auth/login");
  const users = result.data;

  return (
    <>
            <div className="contents">
        <div>
          <h1 className="text-2xl font-semibold">User management</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Search the directory and suspend/reactivate accounts. Actions are
            audited.
          </p>
        </div>

        <div className="mt-6">
          {users.length === 0 ? (
            <p className="text-muted-foreground">No users yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User</TableHead>
                  <TableHead>Roles</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Points</TableHead>
                  <TableHead className="text-right">Solved</TableHead>
                  <TableHead className="text-right">Joined</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell>
                      <p className="font-medium">{u.display_name ?? "—"}</p>
                      <p className="text-xs text-muted-foreground">{u.email}</p>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {u.roles.map((role) => (
                          <Badge key={role} variant="secondary">
                            {role}
                          </Badge>
                        ))}
                        {u.roles.length === 0 ? (
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={u.is_active ? "default" : "destructive"}>
                        {u.is_active ? "Active" : "Suspended"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{u.points}</TableCell>
                    <TableCell className="text-right tabular-nums">{u.solved_count}</TableCell>
                    <TableCell className="text-right text-muted-foreground tabular-nums">
                      {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <UserToggle user={u} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </div>
    </>
  );
}