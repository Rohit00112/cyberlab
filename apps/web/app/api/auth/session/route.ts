import { NextRequest, NextResponse } from "next/server";

import { refreshTokenFlow, fetchMe, REFRESH_COOKIE } from "@/lib/auth/server";
import type { Session, SessionUser } from "@/lib/auth/types";

/**
 * Returns a fresh session (access token + user profile) using the httpOnly
 * refresh cookie. The browser keeps the access token in memory only.
 */
export async function GET(request: NextRequest) {
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;

  if (!refreshToken) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }

  try {
    const tokens = await refreshTokenFlow(refreshToken);
    if (!tokens.access_token) {
      throw new Error("No access token in refresh response");
    }

    const me = (await fetchMe(tokens.access_token)) as SessionUser;
    const session: Session = {
      accessToken: tokens.access_token,
      refreshToken: "",
      expiresIn: Number(tokens.expires_in ?? 300),
      tokenType: tokens.token_type ?? "Bearer",
      user: me,
    };

    const response = NextResponse.json(session);
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