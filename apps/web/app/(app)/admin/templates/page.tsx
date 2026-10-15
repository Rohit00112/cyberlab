"use client";

import { useEffect, useState } from "react";
import { RequireAuth } from "@/components/providers/require-auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api } from "@/lib/api";

interface MachineTemplate {
  id: string;
  slug: string;
  title: string;
  description: string;
  category: string;
  difficulty: string;
  os_type: string;
  architecture: string;
  base_image: string;
  exposure_policy: string;
  status: string;
  version_count: number;
  latest_version?: number | null;
  created_at: string;
}

interface ValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
}

export default function AdminTemplatesPage() {
  const [templates, setTemplates] = useState<MachineTemplate[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Create form state
  const [showCreate, setShowCreate] = useState(false);
  const [slug, setSlug] = useState("");
  const [title, setTitle] = useState("");
  const [baseImage, setBaseImage] = useState("");
  const [category, setCategory] = useState("general");
  const [osType, setOsType] = useState("linux");
  const [validationModal, setValidationModal] = useState<{ id: string; result: ValidationResult } | null>(null);

  function loadTemplates() {
    setLoading(true);
    api
      .get<MachineTemplate[]>("/admin/templates")
      .then(setTemplates)
      .catch((err) => {
        const msg = err instanceof ApiError ? err.detail : "Failed to load templates";
        setError(typeof msg === "string" ? msg : "Failed to load");
        setTemplates([]);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    let ignore = false;
    api
      .get<MachineTemplate[]>("/admin/templates")
      .then((data) => {
        if (!ignore) setTemplates(data);
      })
      .catch((err) => {
        if (!ignore) {
          const msg = err instanceof ApiError ? err.detail : "Failed to load templates";
          setError(typeof msg === "string" ? msg : "Failed to load");
          setTemplates([]);
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    try {
      await api.post("/admin/templates", {
        slug: slug.trim(),
        title: title.trim(),
        base_image: baseImage.trim(),
        category,
        os_type: osType,
        architecture: "x86_64",
        exposure_policy: "vpn_only",
      });
      setSuccess(`Template '${title}' created successfully.`);
      setShowCreate(false);
      setSlug("");
      setTitle("");
      setBaseImage("");
      loadTemplates();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Creation failed";
      setError(typeof msg === "string" ? msg : "Creation failed");
    }
  }

  async function validateTemplate(t: MachineTemplate) {
    setError(null);
    try {
      const res = await api.post<ValidationResult>(`/admin/templates/${t.id}/validate`);
      setValidationModal({ id: t.id, result: res });
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Validation failed";
      setError(typeof msg === "string" ? msg : "Validation failed");
    }
  }

  async function createSnapshotVersion(t: MachineTemplate) {
    setError(null);
    setSuccess(null);
    try {
      await api.post(`/admin/templates/${t.id}/versions`, {});
      setSuccess(`Snapshot version created for '${t.title}'.`);
      loadTemplates();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Version creation failed";
      setError(typeof msg === "string" ? msg : "Version creation failed");
    }
  }

  async function transitionWorkflow(t: MachineTemplate, action: string) {
    setError(null);
    setSuccess(null);
    try {
      await api.post(`/admin/templates/${t.id}/workflow`, { action });
      setSuccess(`Template status updated.`);
      loadTemplates();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Workflow update failed";
      setError(typeof msg === "string" ? msg : "Workflow update failed");
    }
  }

  return (
    <RequireAuth>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Machine Template Builder</h1>
            <p className="text-muted-foreground text-sm">
              Define reusable vulnerable machine images, build immutable versions, and publish templates.
            </p>
          </div>
          <Button onClick={() => setShowCreate(!showCreate)}>
            {showCreate ? "Cancel" : "+ New Template"}
          </Button>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
        {success && <p className="text-sm text-emerald-500">{success}</p>}

        {showCreate && (
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Create Machine Template</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreate} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="title">Template Title</Label>
                    <Input
                      id="title"
                      required
                      placeholder="e.g. Ubuntu 22.04 Insecure Web App"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label htmlFor="slug">Slug (Unique identifier)</Label>
                    <Input
                      id="slug"
                      required
                      placeholder="e.g. ubuntu-insecure-web"
                      value={slug}
                      onChange={(e) => setSlug(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label htmlFor="image">Base Image / Reference</Label>
                    <Input
                      id="image"
                      required
                      placeholder="e.g. cyberlab/web-vuln:latest or /images/app.qcow2"
                      value={baseImage}
                      onChange={(e) => setBaseImage(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label htmlFor="category">Category</Label>
                    <Input
                      id="category"
                      placeholder="web, linux, pwn, etc."
                      value={category}
                      onChange={(e) => setCategory(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label htmlFor="osType">OS Type</Label>
                    <Input
                      id="osType"
                      placeholder="linux, windows, etc."
                      value={osType}
                      onChange={(e) => setOsType(e.target.value)}
                    />
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <Button type="button" variant="outline" onClick={() => setShowCreate(false)}>
                    Cancel
                  </Button>
                  <Button type="submit">Create Template</Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {validationModal && (
          <Card className="border-amber-500/50">
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="text-base">
                Validation Result — {validationModal.result.is_valid ? "Valid" : "Issues Found"}
              </CardTitle>
              <Button size="sm" variant="ghost" onClick={() => setValidationModal(null)}>
                Close
              </Button>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {validationModal.result.errors.length > 0 && (
                <div>
                  <p className="font-semibold text-destructive">Errors:</p>
                  <ul className="list-disc pl-5 text-destructive text-xs space-y-1">
                    {validationModal.result.errors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
              {validationModal.result.warnings.length > 0 && (
                <div>
                  <p className="font-semibold text-amber-500">Warnings:</p>
                  <ul className="list-disc pl-5 text-amber-500 text-xs space-y-1">
                    {validationModal.result.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
              {validationModal.result.errors.length === 0 && validationModal.result.warnings.length === 0 && (
                <p className="text-emerald-500">All checks passed! Template specification is compliant.</p>
              )}
            </CardContent>
          </Card>
        )}

        <div className="grid gap-4">
          {loading && <p className="text-muted-foreground text-sm">Loading templates…</p>}
          {templates && templates.length === 0 && (
            <Card>
              <CardContent className="pt-6 text-muted-foreground text-center">
                No machine templates registered yet. Click &quot;+ New Template&quot; to build one.
              </CardContent>
            </Card>
          )}
          {templates &&
            templates.map((tpl) => (
              <Card key={tpl.id}>
                <CardHeader className="flex-row items-center justify-between pb-2">
                  <div>
                    <CardTitle className="text-base">{tpl.title}</CardTitle>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Slug: <code className="bg-muted px-1 rounded">{tpl.slug}</code> · OS: {tpl.os_type} · Arch: {tpl.architecture}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={tpl.status === "published" ? "default" : "outline"}>
                      {tpl.status.toUpperCase()}
                    </Badge>
                    <Badge variant="secondary">
                      {tpl.version_count} {tpl.version_count === 1 ? "Version" : "Versions"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="text-xs text-muted-foreground space-y-1">
                    <p>Base Image: <code>{tpl.base_image}</code></p>
                    <p>Network Policy: {tpl.exposure_policy}</p>
                  </div>
                  <div className="flex flex-wrap gap-2 pt-2 border-t">
                    <Button size="sm" variant="outline" onClick={() => validateTemplate(tpl)}>
                      Validate Spec
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => createSnapshotVersion(tpl)}>
                      Snapshot Version
                    </Button>
                    {tpl.status === "draft" && (
                      <Button size="sm" variant="outline" onClick={() => transitionWorkflow(tpl, "submit_review")}>
                        Submit Review
                      </Button>
                    )}
                    {tpl.status === "review" && (
                      <Button size="sm" variant="outline" onClick={() => transitionWorkflow(tpl, "approve")}>
                        Approve
                      </Button>
                    )}
                    {tpl.status === "approved" && (
                      <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700" onClick={() => transitionWorkflow(tpl, "publish")}>
                        Publish
                      </Button>
                    )}
                    {tpl.status === "published" && (
                      <Button size="sm" variant="ghost" onClick={() => transitionWorkflow(tpl, "archive")}>
                        Archive
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
        </div>
      </div>
    </RequireAuth>
  );
}
