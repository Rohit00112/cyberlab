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

const textareaClass =
  "flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 " +
  "text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none " +
  "focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

interface CompetitionFormProps {
  mode: "create" | "edit";
  competitionId?: string;
  initial?: {
    title: string;
    description: string;
    rules: string;
    startAt: string;
    endAt: string;
    registrationEndsAt: string;
    allowTeams: boolean;
    maxTeamSize: number;
    scoringMode: "standard" | "override";
  };
}

function toInput(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toISOString().slice(0, 16);
}

export function CompetitionForm({ mode, competitionId, initial }: CompetitionFormProps) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [rules, setRules] = useState(initial?.rules ?? "");
  const [startAt, setStartAt] = useState(initial ? toInput(initial.startAt) : "");
  const [endAt, setEndAt] = useState(initial ? toInput(initial.endAt) : "");
  const [registrationEndsAt, setRegistrationEndsAt] = useState(
    initial ? toInput(initial.registrationEndsAt) : "",
  );
  const [allowTeams, setAllowTeams] = useState(initial?.allowTeams ?? false);
  const [maxTeamSize, setMaxTeamSize] = useState(
    initial ? String(initial.maxTeamSize) : "4",
  );
  const [scoringMode, setScoringMode] = useState<"standard" | "override">(
    initial?.scoringMode ?? "standard",
  );

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const payload: Record<string, unknown> = {
      title: title.trim(),
      description: description.trim() || null,
      rules: rules.trim() || null,
      start_at: startAt ? new Date(startAt).toISOString() : null,
      end_at: endAt ? new Date(endAt).toISOString() : null,
      registration_ends_at: registrationEndsAt
        ? new Date(registrationEndsAt).toISOString()
        : null,
      allow_teams: allowTeams,
      max_team_size: parseInt(maxTeamSize || "4", 10),
      scoring_mode: scoringMode,
    };

    try {
      const result =
        mode === "create"
          ? await api.post<{ id: string }>("/competitions", payload)
          : await api.patch<{ id: string }>(`/competitions/${competitionId}`, payload);
      router.push(`/admin/competitions/${result.id}`);
      router.refresh();
    } catch (err) {
      if (err instanceof ApiError && err.detail) setError(err.detail);
      else setError("Save failed — try again.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="title">Title</Label>
          <Input
            id="title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            maxLength={200}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="description">Description</Label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className={textareaClass}
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="rules">Rules</Label>
          <textarea
            id="rules"
            value={rules}
            onChange={(e) => setRules(e.target.value)}
            className={textareaClass}
            placeholder="Shown to everyone once scheduled."
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="startAt">Start</Label>
          <Input
            id="startAt"
            type="datetime-local"
            value={startAt}
            onChange={(e) => setStartAt(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="endAt">End</Label>
          <Input
            id="endAt"
            type="datetime-local"
            value={endAt}
            onChange={(e) => setEndAt(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="registrationEndsAt">Registration ends</Label>
          <Input
            id="registrationEndsAt"
            type="datetime-local"
            value={registrationEndsAt}
            onChange={(e) => setRegistrationEndsAt(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="scoringMode">Scoring</Label>
          <Select
            value={scoringMode}
            onValueChange={(value) => setScoringMode(value as "standard" | "override")}
          >
            <SelectTrigger className="w-full" id="scoringMode">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="standard">Standard (challenge points)</SelectItem>
              <SelectItem value="override">Override per challenge</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="maxTeamSize">Max team size</Label>
          <Input
            id="maxTeamSize"
            type="number"
            min={1}
            max={10}
            value={maxTeamSize}
            onChange={(e) => setMaxTeamSize(e.target.value)}
            disabled={!allowTeams}
          />
        </div>
        <div className="flex items-end gap-4">
          <label className="flex items-center gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              checked={allowTeams}
              onChange={(e) => setAllowTeams(e.target.checked)}
              className="size-4"
            />
            Allow teams
          </label>
        </div>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : mode === "create" ? "Create competition" : "Save changes"}
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => router.back()}
          disabled={submitting}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}