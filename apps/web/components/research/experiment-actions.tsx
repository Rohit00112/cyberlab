"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";

export function ExperimentActions({ id }: { id: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    try {
      await api.delete(`/research/experiments/${id}`);
      router.refresh();
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.detail ?? "Failed to delete experiment"
          : "Network error";
      alert(typeof message === "string" ? message : "Failed to delete experiment");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Button type="button" variant="outline" size="sm" disabled={busy} onClick={remove}>
      Delete
    </Button>
  );
}