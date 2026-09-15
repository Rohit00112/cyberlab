import { redirect } from "next/navigation";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { Button } from "@/components/ui/button";
import { serverApiGet, serverSessionUser, canServerUser } from "@/lib/api-server";
import type { Announcement } from "@/lib/notifications/types";

export const dynamic = "force-dynamic";

export default async function AnnouncementsPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");

  const canManage = canServerUser(user, "competition.manage");
  const result = await serverApiGet<Announcement[]>("/announcements");
  const announcements = result.ok ? result.data : [];

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-4xl flex-1 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Announcements</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Platform broadcasts and competition notifications.
            </p>
          </div>
          {canManage ? (
            <Link href="/admin/announcements">
              <Button size="sm">Post announcement</Button>
            </Link>
          ) : null}
        </div>

        <div className="mt-6 space-y-4">
          {announcements.length === 0 ? (
            <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
              No announcements posted yet.
            </div>
          ) : (
            announcements.map((a) => (
              <div key={a.id} className="rounded-lg border bg-card p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-lg font-medium">{a.title}</h2>
                    {a.target && a.target !== "all" ? (
                      <span className="mt-0.5 inline-block rounded bg-primary/10 px-2 py-0.5 text-xs text-primary font-mono">
                        {a.target}
                      </span>
                    ) : null}
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(a.created_at).toLocaleDateString(undefined, {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm text-muted-foreground">
                  {a.body}
                </p>
              </div>
            ))
          )}
        </div>
      </main>
    </>
  );
}
