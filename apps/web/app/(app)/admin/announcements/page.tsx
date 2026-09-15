import { redirect } from "next/navigation";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { AnnouncementForm } from "@/components/admin/announcement-form";
import { Button } from "@/components/ui/button";
import { canServerUser, serverApiGet, serverSessionUser } from "@/lib/api-server";
import type { Announcement } from "@/lib/notifications/types";

export const dynamic = "force-dynamic";

export default async function AdminAnnouncementsPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");
  if (!canServerUser(user, "competition.manage")) redirect("/dashboard");

  const result = await serverApiGet<Announcement[]>("/announcements");
  const announcements = result.ok ? result.data : [];

  return (
    <>
      <AppNav />
      <main className="mx-auto w-full max-w-4xl flex-1 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Broadcast Announcements</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Send real-time alerts and platform notices to all users or specific competitions.
            </p>
          </div>
          <Link href="/announcements">
            <Button variant="outline" size="sm">
              Public view
            </Button>
          </Link>
        </div>

        <section className="mt-6 rounded-lg border p-4">
          <h2 className="mb-4 text-base font-medium">New announcement</h2>
          <AnnouncementForm />
        </section>

        <section className="mt-8 rounded-lg border p-4">
          <h2 className="mb-4 text-base font-medium">
            Published announcements ({announcements.length})
          </h2>
          <div className="space-y-3">
            {announcements.length === 0 ? (
              <p className="text-sm text-muted-foreground">No announcements yet.</p>
            ) : (
              announcements.map((a) => (
                <div key={a.id} className="rounded-md border p-4 bg-muted/20">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="font-medium text-sm">{a.title}</h3>
                      <span className="mt-1 inline-block rounded bg-primary/10 px-2 py-0.5 text-xs text-primary font-mono">
                        Target: {a.target}
                      </span>
                    </div>
                    <span className="text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(a.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground whitespace-pre-wrap">
                    {a.body}
                  </p>
                </div>
              ))
            )}
          </div>
        </section>
      </main>
    </>
  );
}
