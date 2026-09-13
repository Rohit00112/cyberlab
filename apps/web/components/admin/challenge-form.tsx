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
import {
  CATEGORY_OPTIONS,
  DIFFICULTY_OPTIONS,
  ENVIRONMENT_OPTIONS,
  STATUS_OPTIONS,
  type Challenge,
  type ChallengeStatus,
  type Difficulty,
} from "@/lib/challenges/types";

interface ChallengeFormProps {
  mode: "create" | "edit";
  initial?: Challenge;
}

const textareaClass =
  "flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 " +
  "text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none " +
  "focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function isPositiveInt(value: string): boolean {
  return /^[1-9]\d*$/.test(value);
}

export function ChallengeForm({ mode, initial }: ChallengeFormProps) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [instructions, setInstructions] = useState(initial?.instructions ?? "");
  const [category, setCategory] = useState(initial?.category ?? CATEGORY_OPTIONS[0].value);
  const [difficulty, setDifficulty] = useState(initial?.difficulty ?? "beginner");
  const [status, setStatus] = useState(initial?.status ?? "draft");
  const [points, setPoints] = useState(initial ? String(initial.points) : "100");
  const [estimatedMinutes, setEstimatedMinutes] = useState(
    initial?.estimated_minutes != null ? String(initial.estimated_minutes) : "",
  );
  const [skillsText, setSkillsText] = useState(initial?.skills.join(", ") ?? "");
  const [prerequisitesText, setPrerequisitesText] = useState(
    initial?.prerequisites.join(", ") ?? "",
  );
  const [hints, setHints] = useState<string[]>(initial?.hints ?? [""]);
  const [hintPenalty, setHintPenalty] = useState(
    initial ? String(initial.hint_penalty) : "0",
  );
  const [flag, setFlag] = useState("");
  const [flagFormat, setFlagFormat] = useState(initial?.flag_format ?? "");
  const [environmentType, setEnvironmentType] = useState(
    initial?.environment_type ?? "none",
  );
  const [labImage, setLabImage] = useState(initial?.lab_config?.image ?? "");
  const [labExpiry, setLabExpiry] = useState(
    initial?.lab_config?.expiry_minutes != null
      ? String(initial.lab_config.expiry_minutes)
      : "",
  );
  const [labMaxInstances, setLabMaxInstances] = useState(
    initial?.lab_config?.max_instances != null
      ? String(initial.lab_config.max_instances)
      : "",
  );

  function updateHint(index: number, value: string) {
    setHints((prev) => prev.map((hint, i) => (i === index ? value : hint)));
  }

  function removeHint(index: number) {
    setHints((prev) => prev.filter((_, i) => i !== index));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    const payload: Record<string, unknown> = {
      title: title.trim(),
      description: description.trim(),
      instructions: instructions.trim() || null,
      category,
      difficulty,
      status,
      points: parseInt(points || "0", 10),
      estimated_minutes: estimatedMinutes ? parseInt(estimatedMinutes, 10) : null,
      skills: splitList(skillsText),
      prerequisites: splitList(prerequisitesText),
      hints: hints.map((hint) => hint.trim()).filter(Boolean),
      hint_penalty: parseInt(hintPenalty || "0", 10),
      flag_format: flagFormat.trim() || null,
      environment_type: environmentType.trim() || "none",
    };
    if (mode === "create") {
      payload.flag = flag.trim() || null;
    } else if (flag.trim()) {
      payload.flag = flag.trim();
    }

    if (environmentType === "docker") {
      payload.lab_config = {
        ...(labImage.trim() ? { image: labImage.trim() } : {}),
        ...(isPositiveInt(labExpiry) ? { expiry_minutes: parseInt(labExpiry, 10) } : {}),
        ...(isPositiveInt(labMaxInstances)
          ? { max_instances: parseInt(labMaxInstances, 10) }
          : {}),
      };
      if (Object.keys(payload.lab_config as Record<string, unknown>).length === 0) {
        payload.lab_config = null;
      }
    } else {
      payload.lab_config = null;
    }

    try {
      const challenge = mode === "create"
        ? await api.post<Challenge>("/challenges", payload)
        : await api.patch<Challenge>(`/challenges/${initial!.id}`, payload);
      if (mode === "create") {
        router.push(`/admin/challenges/${challenge.id}/edit`);
      } else {
        router.push("/admin/challenges");
      }
    } catch (err) {
      if (err instanceof ApiError && err.detail) {
        setError(err.detail);
      } else {
        setError("Save failed — please check the fields and try again.");
      }
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2 grid gap-1.5">
          <Label htmlFor="challenge-title">Title</Label>
          <Input
            id="challenge-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            minLength={1}
            maxLength={200}
          />
        </div>
        <div className="sm:col-span-2 grid gap-3 sm:grid-cols-3">
          <div className="grid gap-1.5">
            <Label htmlFor="challenge-category">Category</Label>
            <Select value={category} onValueChange={(value) => value && setCategory(value)}>
              <SelectTrigger id="challenge-category" className="w-full">
                <SelectValue placeholder="Category" />
              </SelectTrigger>
              <SelectContent>
                {CATEGORY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="challenge-difficulty">Difficulty</Label>
            <Select value={difficulty} onValueChange={(value) => value && setDifficulty(value as Difficulty)}>
              <SelectTrigger id="challenge-difficulty" className="w-full">
                <SelectValue placeholder="Difficulty" />
              </SelectTrigger>
              <SelectContent>
                {DIFFICULTY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="challenge-status">Status</Label>
            <Select value={status} onValueChange={(value) => value && setStatus(value as ChallengeStatus)}>
              <SelectTrigger id="challenge-status" className="w-full">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                {STATUS_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="sm:col-span-2 grid gap-1.5">
          <Label htmlFor="challenge-description">Description</Label>
          <textarea
            id="challenge-description"
            className={textareaClass}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
          />
        </div>
        <div className="sm:col-span-2 grid gap-1.5">
          <Label htmlFor="challenge-instructions">Instructions</Label>
          <textarea
            id="challenge-instructions"
            className={textareaClass}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder="How the student should approach it (optional)"
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="challenge-points">Points</Label>
          <Input
            id="challenge-points"
            type="number"
            min={0}
            value={points}
            onChange={(e) => setPoints(e.target.value)}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="challenge-minutes">Estimated minutes</Label>
          <Input
            id="challenge-minutes"
            type="number"
            min={1}
            value={estimatedMinutes}
            onChange={(e) => setEstimatedMinutes(e.target.value)}
            placeholder="Optional"
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="challenge-skills">Skills</Label>
          <Input
            id="challenge-skills"
            value={skillsText}
            onChange={(e) => setSkillsText(e.target.value)}
            placeholder="Comma-separated, e.g. tcpdump, port-scanning"
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="challenge-prereqs">Prerequisites</Label>
          <Input
            id="challenge-prereqs"
            value={prerequisitesText}
            onChange={(e) => setPrerequisitesText(e.target.value)}
            placeholder="Comma-separated (optional)"
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="challenge-penalty">Hint penalty (per reveal)</Label>
          <Input
            id="challenge-penalty"
            type="number"
            min={0}
            value={hintPenalty}
            onChange={(e) => setHintPenalty(e.target.value)}
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="challenge-flag">Flag</Label>
          <Input
            id="challenge-flag"
            value={flag}
            onChange={(e) => setFlag(e.target.value)}
            placeholder={
              mode === "edit" ? "Leave blank to keep current flag" : "IIC{...}"
            }
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="challenge-flag-format">Flag format</Label>
          <Input
            id="challenge-flag-format"
            value={flagFormat}
            onChange={(e) => setFlagFormat(e.target.value)}
            placeholder="e.g. IIC{...}"
          />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="challenge-env">Environment type</Label>
          <Select value={environmentType} onValueChange={(value) => value && setEnvironmentType(value)}>
            <SelectTrigger id="challenge-env" className="w-full">
              <SelectValue placeholder="Environment" />
            </SelectTrigger>
            <SelectContent>
              {ENVIRONMENT_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {environmentType === "docker" ? (
          <div className="sm:col-span-2 rounded-md border p-4">
            <p className="text-sm font-medium">Docker lab config</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Optional overrides. Expiry is capped server-side; instance limits
              apply per user.
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1.5">
                <Label htmlFor="challenge-lab-image">Image</Label>
                <Input
                  id="challenge-lab-image"
                  value={labImage}
                  onChange={(e) => setLabImage(e.target.value)}
                  placeholder="Sample OS / image reference"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="challenge-lab-expiry">Expiry (minutes)</Label>
                <Input
                  id="challenge-lab-expiry"
                  type="number"
                  min={1}
                  value={labExpiry}
                  onChange={(e) => setLabExpiry(e.target.value)}
                  placeholder="Server default"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="challenge-lab-max-instances">Max instances / user</Label>
                <Input
                  id="challenge-lab-max-instances"
                  type="number"
                  min={1}
                  value={labMaxInstances}
                  onChange={(e) => setLabMaxInstances(e.target.value)}
                  placeholder="Server default"
                />
              </div>
            </div>
          </div>
        ) : null}
        <div className="sm:col-span-2">
          <Label>Hints</Label>
          <div className="mt-2 space-y-2">
            {hints.map((hint, index) => (
              <div key={index} className="flex items-start gap-2">
                <div className="grid flex-1 gap-1.5">
                  <textarea
                    className={textareaClass}
                    value={hint}
                    onChange={(e) => updateHint(index, e.target.value)}
                    placeholder={`Hint ${index + 1}`}
                  />
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => removeHint(index)}
                  disabled={hints.length === 1}
                  className="mt-1 shrink-0"
                >
                  Remove
                </Button>
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setHints((prev) => [...prev, ""])}
            >
              Add hint
            </Button>
          </div>
        </div>
      </div>

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : mode === "create" ? "Create challenge" : "Save changes"}
        </Button>
      </div>
    </form>
  );
}