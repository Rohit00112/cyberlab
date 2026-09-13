"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError, api } from "@/lib/api";
import type { Challenge } from "@/lib/challenges/types";

export function ChallengeActions({ challenge }: { challenge: Challenge }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function togglePublish() {
    setBusy(true);
    setError(null);
    try {
      if (challenge.status === "published") {
        await api.patch<Challenge>(`/challenges/${challenge.id}`, { status: "draft" });
      } else {
        await api.post<Challenge>(`/challenges/${challenge.id}/publish`);
      }
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.detail) setError(err.detail);
      else setError("Action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      await api.delete(`/challenges/${challenge.id}`);
      setConfirmOpen(false);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.detail) setError(err.detail);
      else setError("Delete failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Link
        href={`/admin/challenges/${challenge.id}/edit`}
        className={buttonVariants({ variant: "outline", size: "sm" })}
      >
        Edit
      </Link>
      <Button
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={togglePublish}
      >
        {challenge.status === "published" ? "Unpublish" : "Publish"}
      </Button>
      <Button
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={() => setConfirmOpen(true)}
      >
        Delete
      </Button>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete challenge?</DialogTitle>
            <DialogDescription>
              This permanently deletes “{challenge.title}”. Student submissions are
              cascade-deleted. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={remove}
            >
              {busy ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}