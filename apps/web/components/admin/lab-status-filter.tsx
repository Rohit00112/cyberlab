"use client";

import { useRouter, useSearchParams } from "next/navigation";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LAB_STATUS_LABELS, type Lab } from "@/lib/challenges/types";

type LabStatus = Lab["status"];

const STATUS_OPTIONS: { value: LabStatus; label: string }[] = (
  Object.entries(LAB_STATUS_LABELS) as [LabStatus, string][]
).map(([value, label]) => ({ value, label }));

export function LabStatusFilter() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const status = searchParams.get("status") ?? "all";

  function onValueChange(value: string | null) {
    if (!value || value === "all") {
      router.push("/admin/labs");
    } else {
      router.push(`/admin/labs?status=${encodeURIComponent(value)}`);
    }
  }

  return (
    <Select value={status} onValueChange={onValueChange}>
      <SelectTrigger className="w-56">
        <SelectValue placeholder="Filter by status" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">All statuses</SelectItem>
        {STATUS_OPTIONS.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}