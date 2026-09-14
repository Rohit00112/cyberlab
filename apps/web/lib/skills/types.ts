export interface SkillBrief {
  id: string;
  slug: string;
  name: string;
  icon?: string | null;
}

export interface SkillOut extends SkillBrief {
  description?: string | null;
  path?: string | null;
  is_active: boolean;
  challenge_count: number;
}

export interface SkillEvidence {
  challenge_id: string;
  challenge_title: string;
  difficulty: string;
  earned_points: number;
  solved_at: string;
}

export interface SkillScore {
  skill: SkillBrief;
  score: number;
  solved_count: number;
  total_points: number;
  evidence: SkillEvidence[];
}

export interface SkillProfile {
  user_id: string;
  display_name?: string | null;
  total_points: number;
  solved_count: number;
  skills: SkillScore[];
}

export interface SkillAggregate {
  skill: SkillBrief;
  students_with_evidence: number;
  total_solves: number;
  total_points: number;
  avg_score: number;
}

export interface BadgeOut {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  criteria: Record<string, unknown>;
  icon?: string | null;
  skill_id?: string | null;
  skill_name?: string | null;
  is_active: boolean;
}

export interface BadgeEarned {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  icon?: string | null;
  skill_name?: string | null;
  earned_at: string;
  evidence?: Record<string, unknown> | null;
}

export const VERDICT_LABELS: Record<string, string> = {
  insufficient_data: "Insufficient data",
  too_easy: "Too easy",
  too_difficult: "Too difficult",
  challenging: "Challenging",
  appropriate: "Appropriate",
};

export interface ChallengeDifficulty {
  challenge_id: string;
  slug: string;
  title: string;
  estimated_minutes?: number | null;
  attempts: number;
  distinct_students: number;
  solvers: number;
  success_rate: number;
  median_seconds?: number | null;
  avg_attempts_per_student: number;
  hint_users: number;
  hint_usage: number;
  verdict: string;
}

export interface ChallengeAttempt {
  challenge_id: string;
  slug: string;
  title: string;
  category: string;
  points: number;
  solved: boolean;
  attempts: number;
  earned_points: number;
  hints_revealed: number;
  first_attempt_at?: string | null;
  solved_at?: string | null;
}

export interface StudentAnalyticsBadge {
  code: string;
  name: string;
  icon?: string | null;
  earned_at?: string | null;
  evidence?: Record<string, unknown> | null;
}

export interface StudentAnalytics {
  user_id: string;
  display_name?: string | null;
  email?: string | null;
  total_points: number;
  solved_count: number;
  attempts: number;
  hint_reveals: number;
  badges: StudentAnalyticsBadge[];
  challenges: ChallengeAttempt[];
  skills: SkillScore[];
}