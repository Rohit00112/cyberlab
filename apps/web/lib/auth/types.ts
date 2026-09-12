export interface SessionUser {
  id: string;
  keycloak_sub: string;
  email: string | null;
  display_name: string | null;
  roles: string[];
  permissions: string[];
}

export interface Session {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  tokenType: string;
  user: SessionUser;
}