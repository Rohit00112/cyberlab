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
  hints_count: number;
  hints_revealed: number;
  hint_penalty: number;
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

export const CATEGORIES = [
  "Linux",
  "Networking",
  "Web Security",
  "Cryptography",
  "Digital Forensics",
  "OSINT",
  "System Security",
  "Blue Team",
  "Secure Coding",
  "Cloud Security",
];

export const CATEGORY_OPTIONS = CATEGORIES.map((value) => ({ value, label: value }));

export const STATUS_OPTIONS: { value: ChallengeStatus; label: string }[] = [
  { value: "draft", label: "Draft" },
  { value: "published", label: "Published" },
  { value: "archived", label: "Archived" },
];

export function statusLabel(value: ChallengeStatus): string {
  return STATUS_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

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

export interface SubmissionReview {
  id: string;
  user_id: string;
  display_name?: string | null;
  challenge_id: string;
  challenge_title?: string | null;
  is_correct: boolean;
  earned_points: number;
  created_at: string;
}

export interface PerChallengeStat {
  challenge_id: string;
  slug: string;
  title: string;
  attempts: number;
  solves: number;
}

export interface AnalyticsSummary {
  total_users: number;
  total_submissions: number;
  total_solves: number;
  success_rate: number;
  total_points_awarded: number;
  top_challenges: PerChallengeStat[];
  top_students: LeaderboardEntry[];
}