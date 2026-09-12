import Link from "next/link";

export default function AuthErrorPage() {
  return (
    <main className="flex flex-1 items-center justify-center p-6">
      <div className="text-center">
        <h1 className="text-xl font-semibold">Authentication failed</h1>
        <p className="mt-2 text-muted-foreground">
          The sign-in process did not complete. Please try again.
        </p>
        <Link href="/auth/login" className="mt-4 inline-block text-primary underline">
          Try signing in again
        </Link>
      </div>
    </main>
  );
}