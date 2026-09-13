import { Badge } from "@/components/ui/badge";
import {
  COMPETITION_STATUS_LABELS,
  type CompetitionStatus,
} from "@/lib/competitions/types";

export function CompetitionStatusBadge({ status }: { status: CompetitionStatus }) {
  return (
    <Badge
      variant={
        status === "live"
          ? "default"
          : status === "draft" || status === "archived"
            ? "outline"
            : "secondary"
      }
    >
      {COMPETITION_STATUS_LABELS[status] ?? status}
    </Badge>
  );
}