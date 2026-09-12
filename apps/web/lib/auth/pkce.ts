import crypto from "node:crypto";

export function generatePkcePair(): { verifier: string; challenge: string } {
  const verifier = crypto.randomBytes(32).toString("base64url");
  const challenge = crypto.createHash("sha256").update(verifier).digest("base64url");
  return { verifier, challenge };
}

export function randomString(bytes = 24): string {
  return crypto.randomBytes(bytes).toString("base64url");
}