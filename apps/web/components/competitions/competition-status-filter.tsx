"use client";

import { useRouter, useSearchParams } from "next/navigation";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { COMPETITION_STATUS_OPTIONS } from "@/lib/competitions/types";

export function CompetitionStatusFilter() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const status = searchParams.get("status") ?? "all";

  function onValueChange(value: string | null) {
    if (!value || value === "all") {
      router.push("/competitions");
    } else {
      router.push(`/competitions?status=${encodeURIComponent(value)}`);
    }
  }

  return (
    <Select value={status} onValueChange={onValueChange}>
      <SelectTrigger className="w-56">
        <SelectValue placeholder="Filter by status" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">All statuses</SelectItem>
        {COMPETITION_STATUS_OPTIONS.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}