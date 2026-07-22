import { Card, CardContent } from "./ui/card";
import { Skeleton } from "./ui/skeleton";

export default function RoomCardSkeleton() {
  return (
    <Card className="gap-0 overflow-hidden py-0!">
      <Skeleton className="h-50 w-full rounded-none" />
      <CardContent className="px-4 py-4">
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
          <Skeleton className="h-5 w-16 shrink-0" />
        </div>
        <div className="mb-3 flex gap-1.5">
          <Skeleton className="h-5 w-12" />
          <Skeleton className="h-5 w-12" />
          <Skeleton className="h-5 w-8" />
        </div>
        <div className="flex items-center justify-between border-t border-border pt-3">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-6 w-20" />
        </div>
      </CardContent>
    </Card>
  );
}
