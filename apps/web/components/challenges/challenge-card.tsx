import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { difficultyLabel, type Challenge } from "@/lib/challenges/types";

export function ChallengeCard({ challenge }: { challenge: Challenge }) {
  return (
    <Link href={`/challenges/${challenge.slug}`} className="group focus:outline-none">
      <Card className="h-full transition-colors group-hover:ring-primary group-focus-visible:ring-2 group-focus-visible:ring-primary">
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <CardTitle>{challenge.title}</CardTitle>
            <span className="text-lg font-semibold tabular-nums text-primary">
              {challenge.points}
              <span className="ml-0.5 text-xs font-normal text-muted-foreground">pts</span>
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <Badge variant="secondary">{challenge.category}</Badge>
            <Badge variant="outline">{difficultyLabel(challenge.difficulty)}</Badge>
            {challenge.estimated_minutes ? (
              <span className="text-xs text-muted-foreground">
                ~{challenge.estimated_minutes} min
              </span>
            ) : null}
          </div>
        </CardHeader>
        <CardContent>
          <p className="line-clamp-2 text-muted-foreground">{challenge.description}</p>
          {challenge.skills.length > 0 ? (
            <p className="mt-3 flex flex-wrap gap-1">
              {challenge.skills.slice(0, 3).map((skill) => (
                <span
                  key={skill}
                  className="rounded-md bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
                >
                  {skill}
                </span>
              ))}
              {challenge.skills.length > 3 ? (
                <span className="text-xs text-muted-foreground">
                  +{challenge.skills.length - 3} more
                </span>
              ) : null}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </Link>
  );
}