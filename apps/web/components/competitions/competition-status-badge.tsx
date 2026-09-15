import { StatusBadge } from "@/components/ui/badge";
import {
  COMPETITION_STATUS_LABELS,
  type CompetitionStatus,
} from "@/lib/competitions/types";

const STYLES: Record<CompetitionStatus, "success" | "warning" | "default" | "secondary" | "outline"> = {
  draft: "outline",
  registration: "warning",
  scheduled: "default",
  live: "success",
  finished: "secondary",
  archived: "outline",
};

export function CompetitionStatusBadge({ status }: { status: CompetitionStatus }) {
  return (
    <StatusBadge variant={STYLES[status] ?? "secondary"} className="uppercase">
      {COMPETITION_STATUS_LABELS[status] ?? status}
    </StatusBadge>
  );
}