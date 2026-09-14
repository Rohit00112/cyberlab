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
import type { Challenge } from "@/lib/challenges/types";
import type { LearningPathSummary } from "@/lib/paths/types";

interface PathStepFormProps {
  paths: LearningPathSummary[];
  challenges: Challenge[];
}

export function PathStepForm({ paths, challenges }: PathStepFormProps) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pathId, setPathId] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [stepOrder, setStepOrder] = useState("1");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!pathId || !challengeId) {
      setError("Pick a path and a challenge.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.post(`/paths/${pathId}/steps`, {
        challenge_id: challengeId,
        step_order: Number(stepOrder),
      });
      router.refresh();
      setChallengeId("");
    } catch (err) {
      const message = err instanceof ApiError ? err.detail ?? "Failed to add step" : "Network error";
      setError(typeof message === "string" ? message : "Failed to add step");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="step-path">Path</Label>
          <Select value={pathId} onValueChange={(value) => setPathId(value ?? "")}>
            <SelectTrigger id="step-path">
              <SelectValue placeholder="Select a path" />
            </SelectTrigger>
            <SelectContent>
              {paths.map((path) => (
                <SelectItem key={path.id} value={path.id}>
                  {path.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="step-challenge">Challenge</Label>
          <Select value={challengeId} onValueChange={(value) => setChallengeId(value ?? "")}>
            <SelectTrigger id="step-challenge">
              <SelectValue placeholder="Select a challenge" />
            </SelectTrigger>
            <SelectContent>
              {challenges.map((challenge) => (
                <SelectItem key={challenge.id} value={challenge.id}>
                  {challenge.title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="step-order">Step order</Label>
          <Input
            id="step-order"
            type="number"
            min={1}
            value={stepOrder}
            onChange={(e) => setStepOrder(e.target.value)}
            required
          />
        </div>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Button type="submit" disabled={submitting}>
        {submitting ? "Adding…" : "Add step"}
      </Button>
    </form>
  );
}