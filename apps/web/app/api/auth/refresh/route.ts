import { NextRequest, NextResponse } from "next/server";

import { refreshTokenFlow, REFRESH_COOKIE } from "@/lib/auth/server";

/**
 * Exchanges the refresh cookie for a new access token without touching the
 * full session. Used by the client fetch wrapper on 401 responses.
 */
export async function POST(request: NextRequest) {
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
  if (!refreshToken) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }
  try {
    const tokens = await refreshTokenFlow(refreshToken);
    if (!tokens.access_token) {
      throw new Error("No access token in refresh response");
    }
    const response = NextResponse.json({
      accessToken: tokens.access_token,
      expiresIn: Number(tokens.expires_in ?? 300),
      tokenType: tokens.token_type ?? "Bearer",
    });
    if (tokens.refresh_token) {
      response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, {
        httpOnly: true,
        sameSite: "lax",
        secure: process.env.NODE_ENV === "production",
        path: "/",
        maxAge: 7 * 24 * 3600,
      });
    }
    return response;
  } catch {
    const response = NextResponse.json({ error: "session expired" }, { status: 401 });
    response.cookies.set(REFRESH_COOKIE, "", { httpOnly: true, path: "/", maxAge: -1 });
    return response;
  }
}