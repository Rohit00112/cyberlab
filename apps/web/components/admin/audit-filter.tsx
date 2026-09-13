"use client";

import { useRouter, useSearchParams } from "next/navigation";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AUDIT_EVENTS } from "@/lib/challenges/types";

export function AuditFilter() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const event = searchParams.get("event") ?? "all";

  function onValueChange(value: string | null) {
    if (!value || value === "all") {
      router.push("/admin/audit");
    } else {
      router.push(`/admin/audit?event=${encodeURIComponent(value)}`);
    }
  }

  return (
    <Select value={event} onValueChange={onValueChange}>
      <SelectTrigger className="w-56">
        <SelectValue placeholder="Filter by event" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">All events</SelectItem>
        {AUDIT_EVENTS.map((item) => (
          <SelectItem key={item} value={item}>
            {item}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}