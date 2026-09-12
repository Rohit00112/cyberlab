import { NextRequest, NextResponse } from "next/server";

import {
  STATE_COOKIE,
  PKCE_COOKIE,
  exchangeCodeForTokens,
  cookieOptions,
} from "@/lib/auth/server";

export async function GET(request: NextRequest) {
  const url = request.nextUrl;
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const error = url.searchParams.get("error");

  const expectedState = request.cookies.get(STATE_COOKIE)?.value;
  const verifier = request.cookies.get(PKCE_COOKIE)?.value;

  const response = NextResponse.redirect(url.origin + "/dashboard");
  const clear = { ...cookieOptions, maxAge: -1 };

  if (error || !code || !state || state !== expectedState || !verifier) {
    response.cookies.set(STATE_COOKIE, "", clear);
    response.cookies.set(PKCE_COOKIE, "", clear);
    return NextResponse.redirect(url.origin + "/auth/error");
  }

  try {
    const tokens = await exchangeCodeForTokens(code, verifier);
    response.cookies.set("cyberlab_refresh", tokens.refresh_token, {
      ...cookieOptions,
      maxAge: 7 * 24 * 3600,
    });
  } catch {
    return NextResponse.redirect(url.origin + "/auth/error");
  }

  response.cookies.set(STATE_COOKIE, "", clear);
  response.cookies.set(PKCE_COOKIE, "", clear);
  return response;
}