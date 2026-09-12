import { NextResponse } from "next/server";

import { buildLoginUrl, PKCE_COOKIE, STATE_COOKIE, cookieOptions } from "@/lib/auth/server";

export async function GET() {
  const { url, state, verifier } = await buildLoginUrl();
  const response = NextResponse.redirect(url);
  response.cookies.set(STATE_COOKIE, state, { ...cookieOptions, maxAge: 600 });
  response.cookies.set(PKCE_COOKIE, verifier, { ...cookieOptions, maxAge: 600 });
  return response;
}