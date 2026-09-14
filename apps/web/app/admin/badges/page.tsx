"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";

import { AppNav } from "@/components/app-nav";
import { RequireAuth } from "@/components/providers/require-auth";
import { Badge as UiBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, api } from "@/lib/api";
import { hasPermission } from "@/lib/auth/client";
import type { Badge } from "@/lib/badges/types";

const textareaClass =
  "flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 " +
  "text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none " +
  "focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

export default function AdminBadgesPage() {
  const [badges, setBadges] = useState<Badge[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New badge form state
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [icon, setIcon] = useState("🏅");
  const [criteriaCode, setCriteriaCode] = useState("solver_n");
  const [criteriaValue, setCriteriaValue] = useState("5");

  function loadBadges() {
    api
      .get<Badge[]>("/admin/badges")
      .then((data) => {
        setBadges(data);
        setLoading(false);
      })
      .catch(() => {
        setBadges([]);
        setLoading(false);
      });
  }

  useEffect(() => {
    loadBadges();
  }, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const criteria: Record<string, unknown> = {
        code: criteriaCode,
        value: Number.parseInt(criteriaValue, 10) || 1,
      };
      await api.post("/admin/badges", {
        code,
        name,
        description,
        icon,
        criteria,
        is_active: true,
      });
      setShowCreate(false);
      setCode("");
      setName("");
      setDescription("");
      setIcon("🏅");
      loadBadges();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail ?? "Failed to create badge" : "Network error";
      setError(typeof msg === "string" ? msg : "Failed to create badge");
    } finally {
      setBusy(false);
    }
  }

  async function toggleBadgeStatus(badge: Badge) {
    try {
      await api.patch(`/admin/badges/${badge.id}`, {
        is_active: !badge.is_active,
      });
      setBadges((prev) =>
        prev.map((b) => (b.id === badge.id ? { ...b, is_active: !b.is_active } : b)),
      );
    } catch {
      // ignore
    }
  }

  async function deleteBadge(badgeId: string) {
    if (!confirm("Are you sure you want to delete this badge?")) return;
    try {
      await api.delete(`/admin/badges/${badgeId}`);
      setBadges((prev) => prev.filter((b) => b.id !== badgeId));
    } catch {
      // ignore
    }
  }

  return (
    <RequireAuth>
      <AppNav />
      <main className="mx-auto w-full max-w-6xl flex-1 p-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Badge Management</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Define achievement criteria and configure automated student badges (PRD §34).
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/badges">
              <Button variant="outline" size="sm">
                Public catalogue
              </Button>
            </Link>
            {hasPermission("badge.manage") ? (
              <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
                {showCreate ? "Cancel" : "Create Badge"}
              </Button>
            ) : null}
          </div>
        </div>

        {showCreate ? (
          <Card className="mt-6">
            <CardHeader>
              <CardTitle className="text-base font-semibold">Create New Badge</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreate} className="space-y-4">
                {error ? (
                  <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
                    {error}
                  </div>
                ) : null}

                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="b-code">Unique Code</Label>
                    <Input
                      id="b-code"
                      value={code}
                      onChange={(e) => setCode(e.target.value.toLowerCase().trim())}
                      required
                      placeholder="e.g. solver_15"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="b-name">Display Name</Label>
                    <Input
                      id="b-name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                      placeholder="e.g. Master Investigator"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="b-icon">Icon (Emoji / Char)</Label>
                    <Input
                      id="b-icon"
                      value={icon}
                      onChange={(e) => setIcon(e.target.value)}
                      placeholder="e.g. 🛡️ or 🏆"
                    />
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="b-crit-code">Criteria Evaluator</Label>
                    <select
                      id="b-crit-code"
                      value={criteriaCode}
                      onChange={(e) => setCriteriaCode(e.target.value)}
                      className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    >
                      <option value="first_solve">First Solve (any challenge)</option>
                      <option value="solver_n">Solves Count Threshold (N)</option>
                      <option value="category_champion">Category Champion</option>
                      <option value="lab_session">Lab Pioneer (launch container)</option>
                      <option value="ctf_participant">CTF Participant</option>
                      <option value="ctf_winner">CTF Winner (Top N)</option>
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="b-crit-val">Threshold / Value</Label>
                    <Input
                      id="b-crit-val"
                      type="number"
                      value={criteriaValue}
                      onChange={(e) => setCriteriaValue(e.target.value)}
                      placeholder="e.g. 5"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="b-desc">Description</Label>
                  <textarea
                    id="b-desc"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    className={textareaClass}
                    placeholder="Describe how students earn this badge..."
                  />
                </div>

                <div className="flex gap-2">
                  <Button type="submit" disabled={busy}>
                    {busy ? "Saving..." : "Save Badge"}
                  </Button>
                  <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>
                    Cancel
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        ) : null}

        <div className="mt-6">
          {loading ? (
            <p className="text-muted-foreground text-sm">Loading badges…</p>
          ) : badges.length === 0 ? (
            <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
              No badges configured yet. Use the Create Badge button above or run the seed script.
            </div>
          ) : (
            <div className="rounded-lg border bg-card overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12">Icon</TableHead>
                    <TableHead>Badge Name & Code</TableHead>
                    <TableHead>Description</TableHead>
                    <TableHead>Criteria</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {badges.map((b) => (
                    <TableRow key={b.id}>
                      <TableCell className="text-xl text-center">{b.icon ?? "🏅"}</TableCell>
                      <TableCell>
                        <p className="font-semibold text-sm">{b.name}</p>
                        <p className="font-mono text-xs text-muted-foreground">{b.code}</p>
                      </TableCell>
                      <TableCell className="max-w-xs text-xs text-muted-foreground">
                        {b.description ?? "—"}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {JSON.stringify(b.criteria)}
                      </TableCell>
                      <TableCell>
                        <UiBadge variant={b.is_active ? "default" : "secondary"}>
                          {b.is_active ? "Active" : "Inactive"}
                        </UiBadge>
                      </TableCell>
                      <TableCell className="text-right space-x-2">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => toggleBadgeStatus(b)}
                        >
                          {b.is_active ? "Deactivate" : "Activate"}
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-destructive hover:text-destructive"
                          onClick={() => deleteBadge(b.id)}
                        >
                          Delete
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      </main>
    </RequireAuth>
  );
}
