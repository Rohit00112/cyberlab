"use client";

import { useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";
import {
  difficultyLabel,
  type Challenge,
  type FlagSubmitResult,
} from "@/lib/challenges/types";

export function ChallengeDetail({ challenge }: { challenge: Challenge }) {
  const [revealedHints, setRevealedHints] = useState(0);
  const [flag, setFlag] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<FlagSubmitResult | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!flag.trim() || submitting) return;
    setSubmitting(true);
    try {
      const res = await api.post<FlagSubmitResult>(
        `/challenges/${challenge.id}/submissions`,
        { flag },
      );
      setResult(res);
      if (res.correct) setFlag("");
    } catch (err) {
      const message = err instanceof ApiError ? (err.detail ?? "Submission failed") : "Network error";
      setResult({ correct: false, points: 0, already_solved: false, message });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">{challenge.category}</Badge>
          <Badge variant="outline">{difficultyLabel(challenge.difficulty)}</Badge>
          <span className="text-lg font-semibold tabular-nums text-primary">
            {challenge.points}pts
          </span>
          {challenge.estimated_minutes ? (
            <span className="text-sm text-muted-foreground">
              ~{challenge.estimated_minutes} min
            </span>
          ) : null}
          {challenge.author?.display_name ? (
            <span className="text-xs text-muted-foreground">
              by {challenge.author.display_name}
            </span>
          ) : null}
        </div>
        <h1 className="mt-2 text-2xl font-semibold">{challenge.title}</h1>
        <p className="mt-2 text-muted-foreground">{challenge.description}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Instructions</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="whitespace-pre-line">
                {challenge.instructions || "No additional instructions for this challenge."}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Hints</CardTitle>
              {challenge.hints.length > 0 ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    setRevealedHints(
                      revealedHints >= challenge.hints.length
                        ? 0
                        : challenge.hints.length,
                    )
                  }
                >
                  {revealedHints >= challenge.hints.length ? "Hide hints" : "Reveal hints"}
                </Button>
              ) : null}
            </CardHeader>
            <CardContent>
              {challenge.hints.length === 0 ? (
                <p className="text-muted-foreground">No hints available.</p>
              ) : (
                <ol className="list-decimal space-y-2 pl-5">
                  {challenge.hints.slice(0, revealedHints).map((hint, index) => (
                    <li key={index} className="text-muted-foreground">
                      {hint}
                    </li>
                  ))}
                  {revealedHints === 0 ? (
                    <li className="text-muted-foreground">
                      Hidden — use only if you are stuck.
                    </li>
                  ) : null}
                </ol>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Submit flag</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={onSubmit} className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor={`flag-${challenge.id}`}>Flag</Label>
                  <Input
                    id={`flag-${challenge.id}`}
                    value={flag}
                    onChange={(e) => setFlag(e.target.value)}
                    placeholder={challenge.flag_format ?? "IIC{...}"}
                    autoComplete="off"
                    spellCheck={false}
                  />
                </div>
                <Button type="submit" className="w-full" disabled={submitting || !flag.trim()}>
                  {submitting ? "Checking…" : "Submit"}
                </Button>
                {result ? (
                  <p
                    className={`text-sm ${
                      result.correct ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"
                    }`}
                    aria-live="polite"
                  >
                    {result.correct
                      ? result.already_solved
                        ? `Already solved — ${challenge.points} pts already awarded`
                        : `Correct! +${result.points} pts`
                      : result.message}
                  </p>
                ) : null}
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="space-y-3 pt-2">
              <Button className="w-full" disabled>
                Launch Lab
              </Button>
              <p className="text-xs text-muted-foreground">
                Lab infrastructure arrives in a later stage.
              </p>
              {challenge.flag_format ? (
                <p className="text-xs text-muted-foreground">
                  Flag format: <code className="text-foreground">{challenge.flag_format}</code>
                </p>
              ) : null}
            </CardContent>
          </Card>

          {challenge.skills.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Skills</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-1.5">
                {challenge.skills.map((skill) => (
                  <Badge key={skill} variant="outline">
                    {skill}
                  </Badge>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {challenge.prerequisites.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Prerequisites</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                  {challenge.prerequisites.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}