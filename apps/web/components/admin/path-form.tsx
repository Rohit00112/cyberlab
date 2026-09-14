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

export function PathForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [isPublished, setIsPublished] = useState<string>("draft");

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await api.post("/paths", {
        title,
        slug,
        description: description || null,
        is_published: isPublished === "published",
      });
      router.refresh();
      setTitle("");
      setSlug("");
      setDescription("");
    } catch (err) {
      const message = err instanceof ApiError ? err.detail ?? "Failed to create path" : "Network error";
      setError(typeof message === "string" ? message : "Failed to create path");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="path-title">Title</Label>
          <Input
            id="path-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            placeholder="Web Security Fundamentals"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="path-slug">Slug</Label>
          <Input
            id="path-slug"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
            placeholder="web-security-fundamentals"
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="path-description">Description</Label>
        <Input
          id="path-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What this sequence teaches."
        />
      </div>
      <div className="space-y-1.5">
        <Label>Visibility</Label>
        <Select value={isPublished} onValueChange={(value) => setIsPublished(value ?? "draft")}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Visibility" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="published">Published</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      <Button type="submit" disabled={submitting}>
        {submitting ? "Creating…" : "Create path"}
      </Button>
    </form>
  );
}