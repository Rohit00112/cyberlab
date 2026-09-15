"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/providers/auth-provider";
import { Reveal } from "@/components/motion/reveal";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  ArrowRightIcon,
  BarChart3Icon,
  CheckIcon,
  FlaskConicalIcon,
  RadarIcon,
  ShieldCheckIcon,
  SparklesIcon,
  SwordsIcon,
  TrophyIcon,
  type LucideIcon,
} from "lucide-react";

const TERMINAL_LINES = [
  "$ nmap -sV scan.me 10.10.14.3",
  "$ exploit --chain-cve-2025-4422",
  "$ cat /root/flag.txt",
  "$ flag{d0m4in_m4st3r3d}",
  "$ cyberlab mission complete",
];

const FEATURES: {
  icon: LucideIcon;
  title: string;
  description: string;
  accent: string;
}[] = [
  {
    icon: FlaskConicalIcon,
    title: "Hands-on labs",
    description:
      "Disposable, isolated Docker environments that spin up in seconds and expire on their own.",
    accent: "from-cyan-500/15 to-teal-500/5",
  },
  {
    icon: SwordsIcon,
    title: "Offense & defense",
    description:
      "Exploitation, forensics, phishing detection and privilege escalation — both halves of the craft.",
    accent: "from-violet-500/15 to-fuchsia-500/5",
  },
  {
    icon: TrophyIcon,
    title: "Live competitions",
    description:
      "Contested, timed CTF-style events with realtime leaderboards and badge payouts on finish.",
    accent: "from-amber-500/15 to-orange-500/5",
  },
  {
    icon: RadarIcon,
    title: "Adaptive skill map",
    description:
      "A skill profile model recommends the next best challenge instead of leaving you to wander.",
    accent: "from-emerald-500/15 to-teal-500/5",
  },
];

function TypewriterTerminal() {
  const [visible, setVisible] = useState(0);
  const [chars, setChars] = useState(0);
  const [phase, setPhase] = useState<"typing" | "done">("typing");

  const current = TERMINAL_LINES[Math.min(visible, TERMINAL_LINES.length - 1)];

  useEffect(() => {
    if (phase === "done") return;
    if (visible >= TERMINAL_LINES.length) {
      const t = setTimeout(() => setPhase("done"), 600);
      return () => clearTimeout(t);
    }
    if (chars < current.length) {
      const t = setTimeout(() => setChars((c) => c + 1), 34);
      return () => clearTimeout(t);
    }
    const t = setTimeout(
      () => {
        setVisible((v) => v + 1);
        setChars(0);
      },
      420
    );
    return () => clearTimeout(t);
  }, [chars, visible, phase, current.length]);

  return (
    <div className="overflow-hidden rounded-xl border border-border/80 bg-card/70 shadow-2xl shadow-black/10 backdrop-blur dark:shadow-black/40">
      <div className="flex items-center gap-2 border-b border-border/80 px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-destructive/80" />
        <span className="size-2.5 rounded-full bg-chart-3" />
        <span className="size-2.5 rounded-full bg-chart-2" />
        <span className="ml-3 font-mono text-xs text-muted-foreground">
          operator@cyberlab: ~/missions
        </span>
      </div>
      <div className="min-h-52 space-y-1.5 p-4 font-mono text-[13px] leading-relaxed">
        {TERMINAL_LINES.slice(0, visible).map((line) => (
          <p key={line} className="text-muted-foreground">
            {line}
          </p>
        ))}
        {phase !== "done" ? (
          <p className={visible % 2 === 0 ? "text-primary" : "text-cyber-2"}>
            {current.slice(0, chars)}
            <span className="ml-px inline-block h-4 w-2 translate-y-0.5 animate-pulse bg-primary" />
          </p>
        ) : (
          <p className="font-semibold text-cyber-2">
            {"$ flag{cyberlab_operational} \u2713"}
          </p>
        )}
      </div>
    </div>
  );
}

export default function Home() {
  const { status, login } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") router.replace("/dashboard");
  }, [status, router]);

  return (
    <main className="relative min-h-dvh overflow-hidden bg-background text-foreground">
      {/* Background */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div className="bg-cyber-grid absolute inset-0 opacity-35 [mask-image:radial-gradient(ellipse_70%_55%_at_50%_0%,#000_25%,transparent_75%)] dark:opacity-60" />
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />
        <div className="absolute -top-40 left-1/2 h-96 w-[56rem] -translate-x-1/2 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute top-1/3 -left-32 h-80 w-80 rounded-full bg-cyber-3/10 blur-3xl" />
        <div className="absolute -right-32 bottom-0 h-80 w-80 rounded-full bg-cyber-2/10 blur-3xl" />
      </div>

      <div className="relative mx-auto flex min-h-dvh w-full max-w-6xl flex-col px-4 sm:px-6">
        {/* Top bar */}
        <header className="flex h-16 items-center justify-between">
          <a href="#top" className="flex items-center gap-2">
            <span className="grid size-9 place-items-center rounded-lg bg-gradient-to-br from-primary to-cyber-2 text-primary-foreground shadow-[0_0_18px_-4px_var(--primary)]">
              <ShieldCheckIcon className="size-5" />
            </span>
            <span className="font-display text-base font-bold tracking-tight">
              IIC <span className="text-cyber-gradient">CyberLab</span>
            </span>
          </a>
          <Button
            variant="outline"
            onClick={login}
            disabled={status === "loading"}
            className="shadow-xs"
          >
            Sign in
            <ArrowRightIcon />
          </Button>
        </header>

        {/* Hero */}
        <section id="top" className="relative flex flex-1 flex-col justify-center py-14 lg:flex-row lg:items-center lg:gap-16">
          <Reveal className="max-w-xl">
            <Badge variant="secondary" className="gap-2 rounded-full px-3 py-1 font-medium">
              <span className="relative flex size-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-60" />
                <span className="relative inline-flex size-2 rounded-full bg-primary" />
              </span>
              Cybersecurity training &amp; CTF platform
            </Badge>
            <h1 className="mt-5 text-4xl leading-[1.05] font-bold tracking-tight sm:text-5xl lg:text-[3.4rem]">
              Learn, practice, and defend in a{" "}
              <span className="text-cyber-gradient animate-text-shimmer">live cyber range</span>.
            </h1>
            <p className="mt-5 max-w-lg text-base text-muted-foreground sm:text-lg">
              Work through hands-on challenges in sandboxed labs, watch your skill profile grow,
              and climb the leaderboard in real competitions.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button
                size="lg"
                onClick={login}
                disabled={status === "loading"}
                className="h-11 px-6 text-base"
              >
                {status === "loading" ? "Checking session…" : "Launch the platform"}
                <ArrowRightIcon />
              </Button>
              <Button size="lg" variant="outline" render={<a href="#features" />} className="h-11 px-6 text-base">
                Explore the platform
              </Button>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-muted-foreground">
              {["Live sandbox labs", "Real competitions", "Skill analytics"].map((item) => (
                <span key={item} className="inline-flex items-center gap-1.5">
                  <CheckIcon className="size-4 text-primary" />
                  {item}
                </span>
              ))}
            </div>
          </Reveal>

          <Reveal delay={120} className="mt-12 w-full max-w-md lg:mt-0 lg:max-w-md">
            <TypewriterTerminal />
            <p className="mt-3 text-center font-mono text-xs text-muted-foreground">
              every keystroke logged · every flag scored · every skill mapped
            </p>
          </Reveal>
        </section>

        {/* Proof band */}
        <section className="border-y border-border/70 py-8">
          <div className="flex flex-col items-center justify-between gap-4 text-center sm:flex-row sm:text-left">
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-lg border border-border bg-card text-primary [&_svg]:size-5">
                <BarChart3Icon />
              </span>
              <div>
                <p className="text-sm font-semibold">Built for college cyber teams</p>
                <p className="text-sm text-muted-foreground">Single sign-on. Zero setup for students.</p>
              </div>
            </div>
            <div className="flex items-center gap-8">
              {[
                ["50+", "challenges"],
                ["24/7", "lab uptime"],
                ["100%", "hands-on"],
              ].map(([num, label]) => (
                <div key={label} className="text-center sm:text-right">
                  <p className="font-display text-2xl font-bold text-primary">{num}</p>
                  <p className="text-xs text-muted-foreground">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="scroll-mt-20 py-16">
          <Reveal className="mx-auto max-w-xl text-center">
            <p className="text-xs font-semibold tracking-widest text-primary uppercase">Platform</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">
              Everything a cyber team needs
            </h2>
            <p className="mt-3 text-base text-muted-foreground">
              From your first flag to the podium — one platform that grows with you.
            </p>
          </Reveal>
          <div className="mt-10 grid gap-4 sm:grid-cols-2">
            {FEATURES.map((feature, i) => {
              const Icon = feature.icon;
              return (
                <Reveal key={feature.title} delay={i * 60}>
                  <div className="group relative h-full overflow-hidden rounded-xl border border-border/80 bg-card/50 p-6 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-lg hover:shadow-black/[0.04] dark:hover:shadow-primary/[0.06]">
                    <div className={`absolute inset-x-0 top-0 h-24 bg-gradient-to-b ${feature.accent} opacity-60 transition-opacity group-hover:opacity-100`} />
                    <span className="relative grid size-11 place-items-center rounded-xl border border-border bg-background text-primary shadow-sm [&_svg]:size-5">
                      <Icon />
                    </span>
                    <h3 className="relative mt-4 font-display text-lg font-semibold">{feature.title}</h3>
                    <p className="relative mt-1.5 text-sm text-muted-foreground">{feature.description}</p>
                  </div>
                </Reveal>
              );
            })}
          </div>
          <Reveal className="flex flex-col items-center justify-between gap-4 rounded-xl border border-primary/20 bg-gradient-to-r from-primary/10 to-transparent p-6 sm:flex-row">
            <div className="flex items-center gap-3">
              <SparklesIcon className="size-5 text-primary" />
              <p className="text-sm">
                <span className="font-semibold">Ready to test your skills?</span>{" "}
                <span className="text-muted-foreground">Your first challenge is one click away.</span>
              </p>
            </div>
            <Button onClick={login} disabled={status === "loading"}>
              Start training
              <ArrowRightIcon />
            </Button>
          </Reveal>
        </section>

        {/* Footer */}
        <footer className="flex flex-col items-center justify-between gap-3 border-t border-border py-6 text-xs text-muted-foreground sm:flex-row">
          <span>© {new Date().getFullYear()} IIC CyberLab — internal training platform</span>
          <span className="font-mono text-primary">0x00 :: operational</span>
        </footer>
      </div>
    </main>
  );
}