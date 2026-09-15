"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import {
  AppWindowIcon,
  ArrowRightIcon,
  AwardIcon,
  FlaskConicalIcon,
  KeyRoundIcon,
  RadarIcon,
  ShieldCheckIcon,
  SwordsIcon,
  TrophyIcon,
} from "lucide-react";

const TERMINAL_LINES = [
  "$ nmap -sV scan.me 10.10.14.3",
  "$ exploit --chain-cve-2025-4422",
  "$ cat /root/flag.txt",
  "$ flag{d0m4in_m4st3r3d}",
  "$ cyberlab mission complete",
];

const FEATURES = [
  {
    icon: FlaskConicalIcon,
    title: "Hands-on labs",
    description:
      "Disposable, isolated Docker environments that spin up in seconds and expire on their own.",
  },
  {
    icon: SwordsIcon,
    title: "Offensive & blue-team",
    description:
      "Exploitation, forensics, phishing detection and privilege escalation — build both halves of the skill set.",
  },
  {
    icon: TrophyIcon,
    title: "Live competitions",
    description:
      "Contested, timed CTF-style events with realtime leaderboards and badge payouts on finish.",
  },
  {
    icon: RadarIcon,
    title: "Adaptive skill analytics",
    description:
      "A skill profile model recommends the next best challenge instead of leaving you to wander.",
  },
  {
    icon: AwardIcon,
    title: "Progress that sticks",
    description:
      "Earn badges, build learning paths and keep a portfolio that reflects genuine capability.",
  },
  {
    icon: KeyRoundIcon,
    title: "Enterprise ready",
    description:
      "Single sign-on through your existing identity provider — no extra passwords to manage.",
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
    <div className="overflow-hidden rounded-xl border border-border bg-card/80 shadow-2xl shadow-black/20 backdrop-blur">
      <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-destructive/80" />
        <span className="size-2.5 rounded-full bg-chart-3" />
        <span className="size-2.5 rounded-full bg-chart-2" />
        <span className="ml-3 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <AppWindowIcon className="size-3.5" />
          operator@cyberlab: ~/missions
        </span>
      </div>
      <div className="min-h-56 space-y-1.5 p-4 font-mono text-[13px] leading-relaxed">
        {TERMINAL_LINES.slice(0, visible).map((line) => (
          <p key={line} className="text-muted-foreground">
            {line}
          </p>
        ))}
        {phase !== "done" ? (
          <p className={visible % 2 === 0 ? "text-cyber" : "text-cyber-2"}>
            {current.slice(0, chars)}
            <span className="ml-px inline-block h-4 w-2 translate-y-0.5 animate-pulse bg-cyber" />
          </p>
        ) : (
          <p className="font-bold text-cyber-2">
            {"$ flag{cyberlab_operational} \u2713"}
          </p>
        )}
      </div>
    </div>
  );
}

function rotateIndexes(step: number, size: number) {
  const start = (step * 2) % size;
  return Array.from({ length: size }, (_, i) => (start + i) % size);
}

export default function Home() {
  const { status, login } = useAuth();
  const router = useRouter();
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (status === "authenticated") router.replace("/dashboard");
  }, [status, router]);

  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 6000);
    return () => clearInterval(t);
  }, []);

  const rotated = rotateIndexes(tick, FEATURES.length);

  return (
    <main className="relative min-h-dvh overflow-hidden bg-background text-foreground">
      {/* Background layers */}
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <div
          className="absolute inset-0 opacity-40 dark:opacity-70 [mask-image:radial-gradient(ellipse_75%_60%_at_50%_0%,#000_20%,transparent_75%)] bg-cyber-grid"
        />
        <div className="absolute -top-48 left-1/2 h-[34rem] w-[64rem] -translate-x-1/2 rounded-full bg-cyber/15 blur-3xl" />
        <div className="absolute top-1/2 -left-40 h-96 w-96 rounded-full bg-cyber-3/10 blur-3xl" />
        <div className="absolute -right-32 bottom-0 h-96 w-96 rounded-full bg-cyber-2/10 blur-3xl" />
      </div>

      <div className="relative mx-auto flex min-h-dvh w-full max-w-6xl flex-col px-4 sm:px-6">
        {/* Top bar */}
        <header className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="grid size-9 place-items-center rounded-lg bg-gradient-to-br from-cyber to-cyber-2 text-primary-foreground shadow-[0_0_18px_-4px_var(--cyber)]">
              <ShieldCheckIcon className="size-5" />
            </span>
            <span className="text-base font-semibold tracking-tight">
              IIC <span className="text-cyber-gradient">CyberLab</span>
            </span>
          </div>
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
        <section className="flex flex-1 flex-col items-center justify-center gap-12 py-14 lg:flex-row lg:justify-between">
          <div className="max-w-xl text-center lg:text-left">
            <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-xs font-medium text-muted-foreground">
              <span className="size-1.5 animate-pulse rounded-full bg-cyber" />
              Cybersecurity training &amp; CTF platform
            </span>
            <h1 className="mt-5 text-4xl leading-tight font-bold tracking-tight sm:text-5xl">
              Learn. Practice.
              <br />
              <span className="text-cyber-gradient animate-text-shimmer">
                Compete. Defend.
              </span>
            </h1>
            <p className="mt-5 text-base text-muted-foreground sm:text-lg">
              Work through hands-on challenges in live sandboxes, track a skill
              profile as you grow, and climb the leaderboard in real competitions.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3 lg:justify-start">
              <Button size="lg" onClick={login} disabled={status === "loading"}>
                {status === "loading" ? "Checking session…" : "Launch the platform"}
                <ArrowRightIcon />
              </Button>
              <Button
                size="lg"
                variant="outline"
                render={<a href="#features" />}
              >
                Explore the platform
              </Button>
            </div>
          </div>

          <div className="w-full max-w-md lg:max-w-sm xl:max-w-md">
            <TypewriterTerminal />
            <p className="mt-3 text-center font-mono text-xs text-muted-foreground">
              every keystroke logged · every flag scored · every skill mapped
            </p>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="pb-16 scroll-mt-24">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {/* Rotate visual emphasis across the grid */}
            {rotated.map((idx) => {
              const feature = FEATURES[idx];
              const Icon = feature.icon;
              const featured = rotated[0] === idx;
              return (
                <div
                  key={feature.title}
                  className={`group relative overflow-hidden rounded-xl border p-5 transition-all duration-300 ${
                    featured
                      ? "border-cyber/40 bg-card shadow-[0_0_28px_-10px_var(--cyber)]"
                      : "border-border bg-card/60 hover:-translate-y-0.5 hover:border-cyber/30 hover:shadow-[0_0_22px_-12px_var(--cyber)]"
                  }`}
                >
                  <span className="grid size-10 place-items-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary/20 [&_svg]:size-5">
                    <Icon />
                  </span>
                  <h3 className="mt-4 font-semibold">{feature.title}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">
                    {feature.description}
                  </p>
                </div>
              );
            })}
          </div>
        </section>

        {/* Footer */}
        <footer className="flex flex-col items-center justify-between gap-3 border-t border-border py-6 text-xs text-muted-foreground sm:flex-row">
          <span>IIC CyberLab — internal training platform</span>
          <span className="font-mono text-cyber">0x00 :: operational</span>
        </footer>
      </div>
    </main>
  );
}