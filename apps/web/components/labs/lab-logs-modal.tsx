"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

interface LabStatusResponse {
  status: string;
  provider: string;
  detail?: string;
  running?: boolean;
  ip_address?: string;
  cpu_percent?: number;
  memory_mb?: number;
  uptime_seconds?: number;
  [key: string]: unknown;
}

interface LabLogsResponse {
  lab_id: string;
  provider: string;
  logs: string;
}

export function LabLogsModal({
  labId,
  isOpen,
  onClose,
  title,
}: {
  labId: string;
  isOpen: boolean;
  onClose: () => void;
  title?: string;
}) {
  const [logs, setLogs] = useState<string>("");
  const [statusData, setStatusData] = useState<LabStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [tail, setTail] = useState<number>(100);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [copied, setCopied] = useState(false);
  const terminalRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (!isOpen || !labId) return;

    let active = true;
    async function runFetch() {
      try {
        const [statusRes, logsRes] = await Promise.all([
          api.get<LabStatusResponse>(`/labs/${labId}/status`).catch(() => null),
          api.get<LabLogsResponse>(`/labs/${labId}/logs?tail=${tail}`).catch(() => null),
        ]);
        if (!active) return;
        if (statusRes) setStatusData(statusRes);
        if (logsRes) setLogs(logsRes.logs || "(No console output recorded yet)");
      } catch {
        // ignore
      }
    }

    void runFetch();

    if (!autoRefresh) {
      return () => {
        active = false;
      };
    }

    const interval = setInterval(() => {
      void runFetch();
    }, 5000);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [isOpen, autoRefresh, labId, tail]);

  async function handleManualRefresh() {
    if (!labId) return;
    setLoading(true);
    try {
      const [statusRes, logsRes] = await Promise.all([
        api.get<LabStatusResponse>(`/labs/${labId}/status`).catch(() => null),
        api.get<LabLogsResponse>(`/labs/${labId}/logs?tail=${tail}`).catch(() => null),
      ]);
      if (statusRes) setStatusData(statusRes);
      if (logsRes) setLogs(logsRes.logs || "(No console output recorded yet)");
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs]);

  function copyLogs() {
    navigator.clipboard.writeText(logs);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs animate-in fade-in-0">
      <div className="relative flex max-h-[85vh] w-full max-w-3xl flex-col rounded-xl border border-border bg-background shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-5 py-3.5 bg-muted/30">
          <div className="flex items-center gap-3">
            <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <div>
              <h2 className="text-base font-semibold leading-tight">
                {title ? `Lab Logs: ${title}` : "Container / VM Inspection"}
              </h2>
              <p className="text-xs text-muted-foreground font-mono">ID: {labId}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Live Status Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b bg-muted/10 px-5 py-2.5 text-xs">
          <div className="flex flex-wrap items-center gap-3">
            <Badge variant="outline" className="font-mono text-[11px]">
              Provider: {statusData?.provider ?? "docker"}
            </Badge>
            <Badge
              variant={statusData?.running || statusData?.status === "running" ? "default" : "secondary"}
              className="font-mono text-[11px]"
            >
              State: {statusData?.status ?? "inspecting"}
            </Badge>
            {statusData?.ip_address ? (
              <span className="font-mono text-muted-foreground">
                IP: {statusData.ip_address}
              </span>
            ) : null}
            {statusData?.memory_mb ? (
              <span className="text-muted-foreground">
                RAM: {statusData.memory_mb.toFixed(1)} MB
              </span>
            ) : null}
            {statusData?.cpu_percent !== undefined ? (
              <span className="text-muted-foreground">
                CPU: {statusData.cpu_percent.toFixed(1)}%
              </span>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 cursor-pointer text-muted-foreground hover:text-foreground">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                className="rounded border-input text-primary focus:ring-primary h-3.5 w-3.5"
              />
              <span>Live stream (5s)</span>
            </label>
            <select
              value={tail}
              onChange={(e) => setTail(Number(e.target.value))}
              className="h-7 rounded border border-input bg-transparent px-2 text-xs focus:outline-none"
            >
              <option value={50}>50 lines</option>
              <option value={100}>100 lines</option>
              <option value={250}>250 lines</option>
              <option value={500}>500 lines</option>
            </select>
            <Button size="sm" variant="outline" onClick={handleManualRefresh} disabled={loading} className="h-7 px-2.5 text-xs">
              {loading ? "Refreshing…" : "Refresh"}
            </Button>
            <Button size="sm" variant="outline" onClick={copyLogs} className="h-7 px-2.5 text-xs">
              {copied ? "Copied!" : "Copy"}
            </Button>
          </div>
        </div>

        {/* Terminal Output */}
        <div className="flex-1 bg-neutral-950 p-4 overflow-hidden flex flex-col">
          <pre
            ref={terminalRef}
            className="flex-1 overflow-y-auto font-mono text-xs leading-relaxed text-emerald-400 whitespace-pre-wrap select-text selection:bg-emerald-950 selection:text-white"
          >
            {logs || (loading ? "Connecting to provider socket and reading output buffer…" : "No output.")}
          </pre>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t px-5 py-2.5 bg-muted/20 text-xs text-muted-foreground">
          <span>Standard Output & Standard Error stream</span>
          <Button size="sm" variant="ghost" onClick={onClose} className="h-7">
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
