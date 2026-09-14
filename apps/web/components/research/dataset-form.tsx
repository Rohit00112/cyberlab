"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError, api } from "@/lib/api";
import { DATASET_KINDS, type DatasetKind } from "@/lib/research/types";

export function DatasetForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<DatasetKind>("submissions");
  const [description, setDescription] = useState("");
  const [days, setDays] = useState("30");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const parsed = Number(days);
      await api.post("/research/datasets", {
        name,
        kind,
        description: description || null,
        expires_in_days: Number.isFinite(parsed) && parsed > 0 ? parsed : null,
      });
      router.refresh();
      setName("");
      setDescription("");
      setDays("30");
    } catch (err) {
      const message =
        err instanceof ApiError ? err.detail ?? "Failed to build dataset" : "Network error";
      setError(typeof message === "string" ? message : "Failed to build dataset");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="dataset-name">Name</Label>
          <Input
            id="dataset-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="Solves for spring study"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Kind</Label>
          <Select
            value={kind}
            onValueChange={(value) => setKind((value ?? "submissions") as DatasetKind)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Choose dataset kind" />
            </SelectTrigger>
            <SelectContent>
              {DATASET_KINDS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="dataset-description">Description</Label>
        <Input
          id="dataset-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What this export represents."
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="dataset-days">Expires after (days)</Label>
        <Input
          id="dataset-days"
          type="number"
          min={1}
          max={365}
          value={days}
          onChange={(e) => setDays(e.target.value)}
        />
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Button type="submit" disabled={submitting}>
        {submitting ? "Building…" : "Build dataset"}
      </Button>
    </form>
  );
}