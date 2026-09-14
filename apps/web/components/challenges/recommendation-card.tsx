import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { difficultyLabel, type ChallengeRecommendation } from "@/lib/challenges/types";

export function RecommendationCard({
  recommendation,
}: {
  recommendation: ChallengeRecommendation;
}) {
  return (
    <Link
      href={`/challenges/${recommendation.slug}`}
      className="group focus:outline-none"
    >
      <Card className="h-full transition-colors group-hover:ring-primary group-focus-visible:ring-2 group-focus-visible:ring-primary">
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-sm">{recommendation.title}</CardTitle>
            <span className="shrink-0 text-sm font-semibold tabular-nums text-primary">
              {recommendation.points}
              <span className="ml-0.5 text-xs font-normal text-muted-foreground">pts</span>
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <Badge variant="secondary">{recommendation.category}</Badge>
            <Badge variant="outline">{difficultyLabel(recommendation.difficulty)}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          {recommendation.skills.length > 0 ? (
            <p className="flex flex-wrap gap-1">
              {recommendation.skills.slice(0, 2).map((skill) => (
                <span
                  key={skill.id}
                  className="rounded-md bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
                >
                  {skill.name}
                </span>
              ))}
              {recommendation.skills.length > 2 ? (
                <span className="text-xs text-muted-foreground">
                  +{recommendation.skills.length - 2} more
                </span>
              ) : null}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </Link>
  );
}