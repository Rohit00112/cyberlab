"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/providers/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function Home() {
  const { status, login } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/dashboard");
    }
  }, [status, router]);

  return (
    <main className="flex flex-1 items-center justify-center bg-zinc-50 p-6 dark:bg-black">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">IIC CyberLab</CardTitle>
          <CardDescription>
            Learn. Practice. Compete. Defend. Sign in with your institutional account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            className="w-full"
            onClick={login}
            disabled={status === "loading"}
          >
            {status === "loading" ? "Loading..." : "Sign in"}
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}