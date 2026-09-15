import type { LucideIcon } from "lucide-react";
import {
  AwardIcon,
  BugIcon,
  BrainIcon,
  CircleDotIcon,
  CpuIcon,
  FlagIcon,
  FlaskConicalIcon,
  GlobeIcon,
  KeyRoundIcon,
  LockIcon,
  MedalIcon,
  PackageIcon,
  PuzzleIcon,
  RadioIcon,
  SearchIcon,
  ShieldIcon,
  SkullIcon,
  SwordsIcon,
  TargetIcon,
  TerminalIcon,
  TrophyIcon,
  ZapIcon,
} from "lucide-react";

const CODE_ICONS: Record<string, LucideIcon> = {
  first_solve: FlagIcon,
  solver_5: MedalIcon,
  solver_10: MedalIcon,
  solver_25: TrophyIcon,
  web_champ: GlobeIcon,
  crypto_champ: KeyRoundIcon,
  forensics_champ: SearchIcon,
  linux_champ: TerminalIcon,
  network_champ: RadioIcon,
  blue_team_champ: ShieldIcon,
  lab_pioneer: FlaskConicalIcon,
  ctf_veteran: SwordsIcon,
  ctf_winner: TrophyIcon,
};

const EMOJI_ICONS: Record<string, LucideIcon> = {
  "🚩": FlagIcon,
  "🥉": MedalIcon,
  "🥈": MedalIcon,
  "🥇": TrophyIcon,
  "🌐": GlobeIcon,
  "🔐": LockIcon,
  "🔑": KeyRoundIcon,
  "🔍": SearchIcon,
  "🐧": TerminalIcon,
  "📡": RadioIcon,
  "🛡️": ShieldIcon,
  "🧪": FlaskConicalIcon,
  "⚔️": SwordsIcon,
  "🏆": TrophyIcon,
  "⚡": ZapIcon,
  "💀": SkullIcon,
  "🧠": BrainIcon,
  "🎯": TargetIcon,
  "🐛": BugIcon,
  "📦": PackageIcon,
  "🧩": PuzzleIcon,
  "⚙️": CpuIcon,
  "🔵": CircleDotIcon,
};

export function BadgeIcon({
  badge,
  className,
}: {
  badge: { code: string; icon?: string | null };
  className?: string;
}) {
  const Icon = CODE_ICONS[badge.code] ?? EMOJI_ICONS[(badge.icon ?? "").trim()] ?? AwardIcon;
  return <Icon aria-hidden className={className} />;
}