"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { API_BASE, ApiError, api } from "@/lib/api";
import { getAccessToken, setAccessToken } from "@/lib/auth/client";

type DatasetActionsProps = {
  id: string;
  name: string;
};

async function ensureToken(): Promise<string | null> {
  const token = getAccessToken();
  if (token) return token;
  try {
    const res = await fetch("/api/auth/refresh", { method: "POST" });
    if (!res.ok) return null;
    const data = await res.json();
    setAccessToken(data.accessToken);
    return data.accessToken as string;
  } catch {
    return null;
  }
}

export function DatasetActions({ id, name }: DatasetActionsProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function download() {
    const token = await ensureToken();
    if (!token) return;
    const res = await fetch(
      `${API_BASE}/research/datasets/${id}/download?format=csv`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${name.replaceAll(/[^a-z0-9_-]+/gi, "_")}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function remove() {
    setBusy(true);
    try {
      await api.delete(`/research/datasets/${id}`);
      router.refresh();
    } catch (err) {
      const message =
        err instanceof ApiError ? err.detail ?? "Failed to delete dataset" : "Network error";
      alert(typeof message === "string" ? message : "Failed to delete dataset");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center justify-end gap-2">
      <Button type="button" variant="outline" size="sm" onClick={download}>
        Download
      </Button>
      <Button type="button" variant="outline" size="sm" disabled={busy} onClick={remove}>
        Delete
      </Button>
    </div>
  );
}