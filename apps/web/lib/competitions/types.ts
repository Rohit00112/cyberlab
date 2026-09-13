export type CompetitionStatus =
  | "draft"
  | "registration"
  | "scheduled"
  | "live"
  | "finished"
  | "archived";

export type CompetitionAction =
  | "start_registration"
  | "schedule"
  | "start"
  | "finish"
  | "archive";

export interface CompetitionSummary {
  id: string;
  slug: string;
  title: string;
  description?: string | null;
  status: CompetitionStatus;
  start_at?: string | null;
  end_at?: string | null;
  registration_ends_at?: string | null;
  allow_teams: boolean;
  max_team_size: number;
  scoring_mode: "standard" | "override";
  freeze_leaderboard: boolean;
  frozen_at?: string | null;
  challenge_count: number;
  participant_count: number;
  created_at: string;
  updated_at: string;
}

export interface CompetitionChallengeEntry {
  challenge: {
    id: string;
    slug: string;
    title: string;
    category: string;
    difficulty: string;
    points: number;
    environment_type: string;
  };
  position: number;
  points?: number | null;
}

export interface TeamOut {
  id: string;
  competition_id: string;
  name: string;
  role: "captain" | "member";
  member_count: number;
  members: string[];
}

export interface ParticipantSelf {
  registered: boolean;
  entity_type?: "user" | "team" | null;
  entity_id?: string | null;
  entity_name?: string | null;
  team?: TeamOut | null;
}

export interface Competition {
  id: string;
  slug: string;
  title: string;
  description?: string | null;
  rules?: string | null;
  status: CompetitionStatus;
  start_at?: string | null;
  end_at?: string | null;
  registration_ends_at?: string | null;
  allow_teams: boolean;
  max_team_size: number;
  scoring_mode: "standard" | "override";
  freeze_leaderboard: boolean;
  frozen_at?: string | null;
  challenge_count: number;
  participant_count: number;
  team_count: number;
  challenges: CompetitionChallengeEntry[];
  me?: ParticipantSelf | null;
  created_at: string;
  updated_at: string;
}

export interface LeaderboardEntry {
  rank: number;
  entity_type: "user" | "team";
  entity_id: string;
  display_name: string;
  points: number;
  solved_count: number;
  last_solve_at?: string | null;
}

export const COMPETITION_STATUS_LABELS: Record<CompetitionStatus, string> = {
  draft: "Draft",
  registration: "Registration",
  scheduled: "Scheduled",
  live: "Live",
  finished: "Finished",
  archived: "Archived",
};

export const COMPETITION_STATUS_OPTIONS = Object.entries(
  COMPETITION_STATUS_LABELS,
).map(([value, label]) => ({ value: value as CompetitionStatus, label }));

/** Allowed next action per status (empty = terminal for transitions). */
export const COMPETITION_ACTIONS: Record<CompetitionStatus, CompetitionAction[]> = {
  draft: ["start_registration"],
  registration: ["schedule"],
  scheduled: ["start"],
  live: ["finish"],
  finished: ["archive"],
  archived: [],
};

export const COMPETITION_ACTION_LABELS: Record<CompetitionAction, string> = {
  start_registration: "Open registration",
  schedule: "Schedule",
  start: "Start now",
  finish: "Finish",
  archive: "Archive",
};