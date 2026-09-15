"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type CSSProperties, type ReactNode } from "react";
import {
  AwardIcon,
  BookOpenCheckIcon,
  ChartColumnIcon,
  CpuIcon,
  FlaskConicalIcon,
  GaugeIcon,
  GitBranchIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  MegaphoneIcon,
  MenuIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  RadarIcon,
  ScrollTextIcon,
  SwordsIcon,
  TrophyIcon,
  UserRoundIcon,
  UsersIcon,
  type LucideIcon,
} from "lucide-react";

import { AppLogo } from "@/components/app-logo";
import { NotificationBell } from "@/components/notification-bell";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuth } from "@/components/providers/auth-provider";
import { hasPermission } from "@/lib/auth/client";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  permission?: string;
}

const LEARN_NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboardIcon },
  { href: "/challenges", label: "Challenges", icon: SwordsIcon },
  { href: "/labs", label: "Labs", icon: FlaskConicalIcon, permission: "lab.launch" },
  { href: "/paths", label: "Learning Paths", icon: BookOpenCheckIcon, permission: "learning_path.view" },
];

const COMPETE_NAV: NavItem[] = [
  { href: "/competitions", label: "Competitions", icon: ScrollTextIcon },
  { href: "/leaderboard", label: "Leaderboard", icon: TrophyIcon },
];

const GROW_NAV: NavItem[] = [
  { href: "/skills", label: "Skills", icon: RadarIcon, permission: "skill.view" },
  { href: "/badges", label: "Badges", icon: AwardIcon },
  { href: "/profile", label: "Profile", icon: UserRoundIcon },
];

const MANAGE_NAV: NavItem[] = [
  { href: "/analytics", label: "Analytics", icon: GaugeIcon, permission: "analytics.view" },
  { href: "/admin/challenges", label: "Challenges", icon: SwordsIcon, permission: "challenge.edit" },
  { href: "/admin/users", label: "Users", icon: UsersIcon, permission: "user.view" },
  { href: "/admin/labs", label: "Labs", icon: CpuIcon, permission: "lab.admin" },
  { href: "/admin/competitions", label: "Competitions", icon: ScrollTextIcon, permission: "competition.manage" },
  { href: "/admin/announcements", label: "Announcements", icon: MegaphoneIcon, permission: "competition.manage" },
  { href: "/admin/badges", label: "Badge Admin", icon: AwardIcon, permission: "badge.manage" },
  { href: "/admin/paths", label: "Path Admin", icon: BookOpenCheckIcon, permission: "learning_path.manage" },
  { href: "/admin/audit", label: "Audit Log", icon: ChartColumnIcon, permission: "audit.view" },
  { href: "/research", label: "Research", icon: GitBranchIcon, permission: "analytics.research" },
];

const NAV_SECTIONS: { label: string; items: NavItem[] }[] = [
  { label: "Learn", items: LEARN_NAV },
  { label: "Compete", items: COMPETE_NAV },
  { label: "Grow", items: GROW_NAV },
];

function navIsActive(pathname: string, href: string) {
  if (href === "/dashboard") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function SidebarLink({
  item,
  active,
  collapsed,
}: {
  item: NavItem;
  active: boolean;
  collapsed: boolean;
}) {
  const Icon = item.icon;
  return (
    <Tooltip disabled={!collapsed}>
      <TooltipTrigger
        render={
          <Link
            href={item.href}
            className={cn(
              "relative flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active
                ? "bg-primary/10 text-primary dark:bg-primary/15"
                : "text-muted-foreground hover:bg-accent hover:text-foreground",
              collapsed && "justify-center px-0"
            )}
          />
        }
      >
        {active && !collapsed ? (
          <span className="absolute top-1.5 bottom-1.5 left-0 w-0.5 rounded-full bg-primary" aria-hidden />
        ) : null}
        <Icon className="size-4 shrink-0" />
        {!collapsed ? <span className="truncate">{item.label}</span> : null}
      </TooltipTrigger>
      <TooltipContent side="right">{item.label}</TooltipContent>
    </Tooltip>
  );
}

function SidebarGroup({
  title,
  items,
  pathname,
  collapsed,
  showTitle,
}: {
  title: string;
  items: NavItem[];
  pathname: string;
  collapsed: boolean;
  showTitle: boolean;
}) {
  const visible = items.filter((i) => (i.permission ? hasPermission(i.permission) : true));
  if (visible.length === 0) return null;
  return (
    <div>
      {showTitle && !collapsed ? (
        <p className="px-2.5 pb-1.5 text-[11px] font-semibold tracking-wider text-muted-foreground/80 uppercase">
          {title}
        </p>
      ) : null}
      <div className="flex flex-col gap-0.5">
        {visible.map((item) => (
          <SidebarLink
            key={item.href}
            item={item}
            active={navIsActive(pathname, item.href)}
            collapsed={collapsed}
          />
        ))}
      </div>
    </div>
  );
}

function SidebarNav({
  pathname,
  collapsed,
}: {
  pathname: string;
  collapsed: boolean;
}) {
  const showTitle = !collapsed;
  return (
    <nav
      className={cn(
        "flex flex-col gap-5 overflow-y-auto px-3 py-4",
        collapsed && "gap-3 items-center"
      )}
    >
      {NAV_SECTIONS.map((section) => (
        <SidebarGroup
          key={section.label}
          title={section.label}
          items={section.items}
          pathname={pathname}
          collapsed={collapsed}
          showTitle={showTitle}
        />
      ))}
      <SidebarGroup
        title="Manage"
        items={MANAGE_NAV}
        pathname={pathname}
        collapsed={collapsed}
        showTitle={showTitle}
      />
    </nav>
  );
}

function SidebarHeader({ collapsed }: { collapsed: boolean }) {
  return (
    <div className={cn("flex h-14 items-center border-b border-border/70 px-4", collapsed && "justify-center px-2")}>
      <AppLogo compact={collapsed} />
    </div>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();
  const name = user?.display_name ?? user?.email ?? "User";
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <button className="flex h-8 items-center gap-2 rounded-full pr-1.5 ring-1 ring-border transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring outline-none">
            <Avatar className="size-6">
              <AvatarFallback>{initials || "U"}</AvatarFallback>
            </Avatar>
            <span className="hidden max-w-24 truncate text-sm font-medium lg:block">{name}</span>
          </button>
        }
      >
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuLabel>
            <span className="block truncate">{name}</span>
            <span className="block truncate text-xs font-normal text-muted-foreground">{user?.email}</span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem render={<Link href="/profile" />}>
            <UserRoundIcon className="size-4" />
            Profile
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={logout}>
            <LogOutIcon className="size-4" />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenuTrigger>
    </DropdownMenu>
  );
}

function MobileNav({ pathname }: { pathname: string }) {
  const { logout } = useAuth();

  return (
    <Sheet>
      <SheetTrigger
        render={<Button variant="ghost" size="icon-sm" className="lg:hidden" aria-label="Open menu" />}
      >
        <MenuIcon />
      </SheetTrigger>
      <SheetContent side="left" className="w-72 p-0">
        <SheetHeader className="border-b border-border p-4">
          <SheetTitle>
            <AppLogo />
          </SheetTitle>
        </SheetHeader>
        <SidebarNav pathname={pathname} collapsed={false} />
        <div className="mt-auto flex items-center justify-between border-t border-border p-4">
          <Button variant="ghost" size="sm" onClick={logout}>
            <LogOutIcon className="size-4" />
            Sign out
          </Button>
          <ThemeToggle />
        </div>
      </SheetContent>
    </Sheet>
  );
}

function findActiveItem(pathname: string) {
  const all = [
    ...NAV_SECTIONS.flatMap((s) => s.items.map((i) => ({ ...i, section: s.label }))),
    ...MANAGE_NAV.map((i) => ({ ...i, section: "Manage" })),
  ];
  const active = all.find((item) => navIsActive(pathname, item.href));
  if (active) return active;
  return null;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const active = findActiveItem(pathname);

  return (
    <TooltipProvider delay={0}>
      <div className="flex min-h-dvh">
        {/* Desktop sidebar */}
        <aside
          className={cn(
            "fixed inset-y-0 left-0 z-40 hidden w-60 flex-col border-r border-border/70 bg-sidebar transition-[width] duration-200 lg:flex",
            collapsed && "w-14"
          )}
        >
          <SidebarHeader collapsed={collapsed} />
          <SidebarNav pathname={pathname} collapsed={collapsed} />
          <div className={cn("mt-auto flex items-center border-t border-border/70 p-3", collapsed && "justify-center")}>
            <ThemeToggle />
            {!collapsed ? (
              <span className="ml-2 font-mono text-[11px] text-muted-foreground">v0.1 / ctf</span>
            ) : null}
          </div>
        </aside>

        {/* Main column */}
        <div
          className="flex min-w-0 flex-1 flex-col transition-[padding] duration-200 lg:pl-[var(--shell-pad)]"
          style={{ "--shell-pad": collapsed ? "3.5rem" : "15rem" } as CSSProperties}
        >
          <header className="sticky top-0 z-40 border-b border-border/70 bg-background/80 backdrop-blur-md">
            <div className="flex h-14 items-center gap-2 px-4 sm:px-6">
              <Button
                variant="ghost"
                size="icon-sm"
                className="hidden lg:inline-flex"
                onClick={() => setCollapsed((c) => !c)}
                aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                {collapsed ? <PanelLeftOpenIcon /> : <PanelLeftCloseIcon />}
              </Button>
              <MobileNav pathname={pathname} />

              <div className="min-w-0">
                {active ? (
                  <>
                    <p className="text-[11px] leading-none font-medium text-muted-foreground uppercase tracking-wider">
                      {active.section}
                    </p>
                    <h1 className="truncate font-display text-sm font-semibold">{active.label}</h1>
                  </>
                ) : null}
              </div>

              <div className="ml-auto flex shrink-0 items-center gap-1">
                <NotificationBell />
                <span className="hidden md:inline-flex">
                  <UserMenu />
                </span>
              </div>
            </div>
          </header>

          <main className="mx-auto w-full max-w-6xl flex-1 px-4 pt-6 pb-12 sm:px-6">{children}</main>
        </div>
      </div>
    </TooltipProvider>
  );
}