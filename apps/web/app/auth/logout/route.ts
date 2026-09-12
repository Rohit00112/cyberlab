import { NextResponse } from "next/server";

import { clearAuthCookies } from "@/lib/auth/server";

export async function GET() {
  await clearAuthCookies();
  return NextResponse.redirect(new URL("/", process.env.NEXT_PUBLIC_WEB_ORIGIN ?? "http://localhost:3000"));
}