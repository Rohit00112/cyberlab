/** Research platform API types (Phase 6). */

export type DatasetKind =
  | "submissions"
  | "skill_profiles"
  | "badges"
  | "hints"
  | "labs"
  | "learning_progress"
  | "engagements"
  | "all";

export interface ResearchDataset {
  id: string;
  name: string;
  description?: string | null;
  kind: string;
  pseudonymized: boolean;
  row_count: number;
  file_ref?: string | null;
  created_by?: string | null;
  expires_at?: string | null;
  created_at: string;
}

export interface SourceRecommendationMetrics {
  source: string;
  served: number;
  accepted: number;
  solved: number;
  acceptance_rate: number;
  completion_rate: number;
}

export interface ResearchMetrics {
  learning: {
    assessed_users: number;
    completion_rate: number;
    avg_skill_delta: number;
    retention_rate: number;
    median_days_to_competency: number | null;
  };
  engagement: {
    weekly_active_users: number;
    challenges_attempted: number;
    hints_used: number;
    median_return_days: number | null;
  };
  challenge_quality: {
    challenge_id: string;
    slug: string;
    title: string;
    success_rate: number;
    median_solve_seconds: number | null;
    abandonment_rate: number;
  }[];
  recommendations: {
    served: number;
    accepted: number;
    solved: number;
    acceptance_rate: number;
    completion_rate: number;
    per_source?: SourceRecommendationMetrics[];
  };
  generated_at: string;
}

export type GraphNodeType = "skill" | "challenge" | "category";
export type GraphRelation = "requires" | "in" | "co_solved" | "co_required" | "step";

export interface GraphNode {
  id: string;
  type: GraphNodeType;
  label: string;
  meta: Record<string, unknown>;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: GraphRelation;
  weight: number;
}

export interface ResearchGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  generated_at: string;
}

export interface ResearchExperiment {
  id: string;
  name: string;
  description?: string | null;
  model_ref: string;
  params?: Record<string, unknown> | null;
  metrics?: Record<string, unknown> | null;
  status: string;
  created_by?: string | null;
  created_at: string;
}

export const DATASET_KINDS: { value: DatasetKind; label: string }[] = [
  { value: "submissions", label: "Submissions" },
  { value: "skill_profiles", label: "Skill profiles" },
  { value: "badges", label: "Badges" },
  { value: "hints", label: "Hint reveals" },
  { value: "labs", label: "Lab instances" },
  { value: "learning_progress", label: "Learning progress" },
  { value: "engagements", label: "Engagements" },
  { value: "all", label: "All (union)" },
];