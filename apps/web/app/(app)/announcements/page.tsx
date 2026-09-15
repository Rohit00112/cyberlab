import { redirect } from "next/navigation";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { serverApiGet, serverSessionUser, canServerUser } from "@/lib/api-server";
import type { Announcement } from "@/lib/notifications/types";
import { MegaphoneIcon } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function AnnouncementsPage() {
  const user = await serverSessionUser();
  if (!user) redirect("/auth/login");

  const canManage = canServerUser(user, "competition.manage");
  const result = await serverApiGet<Announcement[]>("/announcements");
  const announcements = result.ok ? result.data : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Announcements</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Platform broadcasts and competition notifications.
          </p>
        </div>
        {canManage ? (
          <Button render={<Link href="/admin/announcements" />}>
            <MegaphoneIcon />
            Post announcement
          </Button>
        ) : null}
      </div>

      <div className="space-y-3">
        {announcements.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border py-16 text-center text-sm text-muted-foreground">
            No announcements posted yet.
          </div>
        ) : (
          announcements.map((announcement, idx) => (
            <div
              key={announcement.id}
              className="group relative rounded-xl border border-border/80 bg-card p-5 transition-all duration-200 hover:border-primary/25 hover:shadow-lg hover:shadow-black/[0.04] dark:hover:shadow-primary/[0.05]"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  {idx === 0 ? (
                    <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary [&_svg]:size-4.5">
                      <MegaphoneIcon />
                    </span>
                  ) : null}
                  <div>
                    <h2 className="font-display text-base font-semibold leading-snug">
                      {announcement.title}
                    </h2>
                    <div className="mt-1 flex items-center gap-2">
                      {announcement.target && announcement.target !== "all" ? (
                        <Badge variant="secondary" className="font-mono text-[11px]">
                          {announcement.target}
                        </Badge>
                      ) : (
                        <Badge variant="ghost" className="font-mono text-[11px]">
                          broadcast
                        </Badge>
                      )}
                      <span className="text-xs text-muted-foreground">
                        {new Date(announcement.created_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
              <p className="mt-3 whitespace-pre-wrap text-sm text-muted-foreground">
                {announcement.body}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}