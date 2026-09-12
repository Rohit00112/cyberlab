export type Difficulty = "beginner" | "intermediate" | "advanced";
export type ChallengeStatus = "draft" | "published" | "archived";

export interface ChallengeAuthor {
  id: string;
  display_name?: string | null;
}

export interface Challenge {
  id: string;
  slug: string;
  title: string;
  description: string;
  instructions?: string | null;
  category: string;
  difficulty: Difficulty;
  points: number;
  estimated_minutes?: number | null;
  skills: string[];
  prerequisites: string[];
  hints: string[];
  flag_format?: string | null;
  environment_type: string;
  author?: ChallengeAuthor | null;
  status: ChallengeStatus;
  version: number;
  created_at: string;
  updated_at: string;
}

export const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

export const DIFFICULTY_OPTIONS = Object.entries(DIFFICULTY_LABELS).map(([value, label]) => ({
  value: value as Difficulty,
  label,
}));

export function difficultyLabel(value: Difficulty): string {
  return DIFFICULTY_LABELS[value] ?? value;
}

export function challengePointsLabel(challenge: Challenge): string {
  return `${challenge.points} pts`;
}

export interface FlagSubmitResult {
  correct: boolean;
  points: number;
  already_solved: boolean;
  message: string;
}

export interface UserStats {
  points: number;
  solved_count: number;
  attempts: number;
}

export interface LeaderboardEntry {
  rank: number;
  user_id: string;
  display_name?: string | null;
  points: number;
  solved_count: number;
}