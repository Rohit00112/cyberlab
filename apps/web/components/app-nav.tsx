"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  AwardIcon,
  BookOpenCheckIcon,
  ChartColumnIcon,
  ChevronDownIcon,
  CpuIcon,
  FlaskConicalIcon,
  GaugeIcon,
  LayoutDashboardIcon,
  LogOutIcon,
  MegaphoneIcon,
  MenuIcon,
  RadarIcon,
  ScrollTextIcon,
  SwordsIcon,
  TrophyIcon,
  UserRoundIcon,
  UsersIcon,
} from "lucide-react";

import { AppLogo } from "@/components/app-logo";
import { NotificationBell } from "@/components/notification-bell";
import { ThemeToggle } from "@/components/theme-toggle";
import { useAuth } from "@/components/providers/auth-provider";
import { hasPermission } from "@/lib/auth/client";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboardIcon;
  permission?: string;
}

const PRIMARY_NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboardIcon },
  { href: "/challenges", label: "Challenges", icon: SwordsIcon },
  { href: "/leaderboard", label: "Leaderboard", icon: TrophyIcon },
  { href: "/competitions", label: "Competitions", icon: ScrollTextIcon },
  { href: "/badges", label: "Badges", icon: AwardIcon },
  { href: "/labs", label: "Labs", icon: FlaskConicalIcon, permission: "lab.launch" },
  { href: "/paths", label: "Learning Paths", icon: BookOpenCheckIcon, permission: "learning_path.view" },
  { href: "/skills", label: "Skills", icon: RadarIcon, permission: "skill.view" },
];

const ADMIN_NAV: NavItem[] = [
  { href: "/analytics", label: "Analytics", icon: GaugeIcon, permission: "analytics.view" },
  { href: "/admin/challenges", label: "Challenges", icon: SwordsIcon, permission: "challenge.edit" },
  { href: "/admin/users", label: "Users", icon: UsersIcon, permission: "user.view" },
  { href: "/admin/labs", label: "Labs", icon: CpuIcon, permission: "lab.admin" },
  { href: "/admin/competitions", label: "Competitions", icon: ScrollTextIcon, permission: "competition.manage" },
  { href: "/admin/announcements", label: "Announcements", icon: MegaphoneIcon, permission: "competition.manage" },
  { href: "/admin/badges", label: "Badge Admin", icon: AwardIcon, permission: "badge.manage" },
  { href: "/admin/paths", label: "Path Admin", icon: BookOpenCheckIcon, permission: "learning_path.manage" },
  { href: "/admin/audit", label: "Audit Log", icon: ChartColumnIcon, permission: "audit.view" },
  { href: "/research", label: "Research", icon: FlaskConicalIcon, permission: "analytics.research" },
];

function navIsActive(pathname: string, href: string) {
  if (href === "/dashboard") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLinkButton({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm font-medium whitespace-nowrap transition-colors",
        active
          ? "bg-primary/10 text-primary"
          : "text-muted-foreground hover:bg-muted hover:text-foreground"
      )}
    >
      <Icon className="size-4" />
      {item.label}
    </Link>
  );
}

function AdminDropdown({ pathname }: { pathname: string }) {
  const items = ADMIN_NAV.filter((i) => (i.permission ? hasPermission(i.permission) : true));
  if (items.length === 0) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              "gap-1 text-sm font-medium",
              items.some((i) => navIsActive(pathname, i.href))
                ? "text-primary"
                : "text-muted-foreground"
            )}
          />
        }
      >
        Manage
        <ChevronDownIcon className="size-3.5 opacity-70" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        {items.map((item) => {
          const Icon = item.icon;
          return (
            <DropdownMenuItem key={item.href} render={<Link href={item.href} />}>
              <Icon className="size-4" />
              {item.label}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
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
          <button className="flex items-center gap-2 rounded-full p-0.5 pr-1.5 ring-1 ring-border transition-colors hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring outline-none">
            <Avatar className="size-7">
              <AvatarFallback>{initials || "U"}</AvatarFallback>
            </Avatar>
            <span className="hidden max-w-28 truncate text-sm font-medium sm:block">
              {name}
            </span>
            <ChevronDownIcon className="size-3.5 text-muted-foreground" />
          </button>
        }
      >
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuLabel>
            <span className="block truncate">{name}</span>
            <span className="block truncate text-xs font-normal text-muted-foreground">
              {user?.email}
            </span>
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
  const adminItems = ADMIN_NAV.filter((i) => (i.permission ? hasPermission(i.permission) : true));
  const visiblePrimary = PRIMARY_NAV.filter((i) =>
    i.permission ? hasPermission(i.permission) : true
  );

  return (
    <Sheet>
      <SheetTrigger
        render={
          <Button variant="ghost" size="icon-sm" className="md:hidden" aria-label="Open menu" />
        }
      >
        <MenuIcon />
      </SheetTrigger>
      <SheetContent side="right" className="w-72 p-0">
        <SheetHeader className="border-b border-border p-4">
          <SheetTitle>
            <AppLogo />
          </SheetTitle>
        </SheetHeader>
        <nav className="flex flex-col gap-1 overflow-y-auto p-3">
          {visiblePrimary.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  navIsActive(pathname, item.href)
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )}
              >
                <Icon className="size-4" />
                {item.label}
              </Link>
            );
          })}

          {adminItems.length > 0 ? (
            <>
              <p className="px-3 pt-4 pb-1 text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
                Manage
              </p>
              {adminItems.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      navIsActive(pathname, item.href)
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                    )}
                  >
                    <Icon className="size-4" />
                    {item.label}
                  </Link>
                );
              })}
            </>
          ) : null}
        </nav>
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

export function AppNav() {
  const pathname = usePathname();
  const { user } = useAuth();
  const visiblePrimary = PRIMARY_NAV.filter((i) =>
    i.permission ? hasPermission(i.permission) : true
  );

  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
        <AppLogo className="mr-1 hidden sm:flex" />
        <AppLogo compact className="sm:hidden" />

        <nav className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto scrollbar-none md:gap-1">
          {visiblePrimary.map((item) => (
            <NavLinkButton key={item.href} item={item} active={navIsActive(pathname, item.href)} />
          ))}
          {user ? <AdminDropdown pathname={pathname} /> : null}
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-1">
          <NotificationBell />
          <span className="hidden md:inline-flex">
            <ThemeToggle />
          </span>
          {user ? (
            <span className="hidden md:inline-flex">
              <UserMenu />
            </span>
          ) : null}
          <MobileNav pathname={pathname} />
        </div>
      </div>
    </header>
  );
}