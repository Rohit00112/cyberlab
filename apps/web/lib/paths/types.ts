export interface LearningPathSummary {
  id: string;
  slug: string;
  title: string;
  description?: string | null;
  is_published: boolean;
}

export type LearningPathStepStatus = "completed" | "unlocked" | "locked";

export interface LearningPathStep {
  challenge_id: string;
  title: string;
  step_order: number;
  status: LearningPathStepStatus;
}

export interface LearningPathDetail extends LearningPathSummary {
  steps: LearningPathStep[];
}

export const STEP_STATUS_LABELS: Record<LearningPathStepStatus, string> = {
  completed: "Completed",
  unlocked: "Unlocked",
  locked: "Locked",
};

export function pathProgress(path: LearningPathDetail): number {
  if (path.steps.length === 0) return 0;
  const completed = path.steps.filter((s) => s.status === "completed").length;
  return Math.round((completed / path.steps.length) * 100);
}