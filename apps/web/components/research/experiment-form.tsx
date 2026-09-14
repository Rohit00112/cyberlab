"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";

export function ExperimentForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [modelRef, setModelRef] = useState("");
  const [description, setDescription] = useState("");
  const [paramsText, setParamsText] = useState("");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    let params: Record<string, unknown> | undefined;
    if (paramsText.trim()) {
      try {
        params = JSON.parse(paramsText);
      } catch {
        setError("Params must be valid JSON (e.g. {\"hidden\": 64})");
        setSubmitting(false);
        return;
      }
    }
    try {
      await api.post("/research/experiments", {
        name,
        model_ref: modelRef,
        description: description || null,
        params: params ?? null,
      });
      router.refresh();
      setName("");
      setModelRef("");
      setDescription("");
      setParamsText("");
    } catch (err) {
      const message =
        err instanceof ApiError ? err.detail ?? "Failed to register experiment" : "Network error";
      setError(typeof message === "string" ? message : "Failed to register experiment");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="exp-name">Name</Label>
          <Input
            id="exp-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="gnn-skills-cooccurrence"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="exp-model">Model reference</Label>
          <Input
            id="exp-model"
            value={modelRef}
            onChange={(e) => setModelRef(e.target.value)}
            required
            placeholder="GNN-v1"
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="exp-description">Description</Label>
        <Input
          id="exp-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Hypothesis being tested, data used, etc."
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="exp-params">Params (JSON)</Label>
        <Input
          id="exp-params"
          value={paramsText}
          onChange={(e) => setParamsText(e.target.value)}
          placeholder='{"hidden": 64, "epochs": 50}'
        />
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Button type="submit" disabled={submitting}>
        {submitting ? "Registering…" : "Register experiment"}
      </Button>
    </form>
  );
}