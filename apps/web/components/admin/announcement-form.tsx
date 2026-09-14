"use client";

import { useRouter } from "next/navigation";
import { useState, type ChangeEvent, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";

const textareaClass =
  "flex min-h-[100px] w-full rounded-md border border-input bg-transparent px-3 py-2 " +
  "text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none " +
  "focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

export function AnnouncementForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [target, setTarget] = useState("all");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setSuccess(false);

    try {
      await api.post("/announcements", {
        title,
        body,
        target: target || "all",
      });
      setSuccess(true);
      setTitle("");
      setBody("");
      setTarget("all");
      router.refresh();
    } catch (err) {
      const message =
        err instanceof ApiError ? err.detail ?? "Failed to post announcement" : "Network error";
      setError(typeof message === "string" ? message : "Failed to post announcement");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      {error ? (
        <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
          {error}
        </div>
      ) : null}
      {success ? (
        <div className="rounded-md bg-emerald-500/15 p-3 text-sm text-emerald-500">
          Announcement broadcast successfully!
        </div>
      ) : null}

      <div className="space-y-1.5">
        <Label htmlFor="ann-title">Title</Label>
        <Input
          id="ann-title"
          value={title}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setTitle(e.target.value)}
          required
          placeholder="Competition Starts Tomorrow at 10:00 AM UTC"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="ann-target">Target Scope</Label>
        <Input
          id="ann-target"
          value={target}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setTarget(e.target.value)}
          required
          placeholder="all or competition:slug"
        />
        <p className="text-xs text-muted-foreground">
          Use &quot;all&quot; to broadcast to the entire platform, or a competition tag.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="ann-body">Announcement Body</Label>
        <textarea
          id="ann-body"
          value={body}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setBody(e.target.value)}
          required
          rows={4}
          className={textareaClass}
          placeholder="Please note that challenges will unlock automatically. Best of luck!"
        />
      </div>

      <Button type="submit" disabled={submitting}>
        {submitting ? "Broadcasting..." : "Broadcast Announcement"}
      </Button>
    </form>
  );
}
