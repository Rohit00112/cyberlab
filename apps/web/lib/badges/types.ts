/** Badge and achievement types (Phase 4, PRD §34). */

export interface Badge {
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

export interface BadgeCreate {
  code: string;
  name: string;
  description?: string;
  criteria: Record<string, unknown>;
  icon?: string;
  skill_id?: string | null;
  is_active?: boolean;
}

export interface BadgeUpdate {
  name?: string;
  description?: string;
  criteria?: Record<string, unknown>;
  icon?: string;
  skill_id?: string | null;
  is_active?: boolean;
}
