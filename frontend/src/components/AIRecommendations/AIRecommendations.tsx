import { useRooms } from "../../hooks/useRooms";

export default function AIRecommendations() {
  const { data: rooms = [] } = useRooms();
  const aiPicks = rooms.filter((r) => r.featured && r.available).slice(0, 2);

  return (
    <div className="mx-auto max-w-300 px-4 pb-8 sm:px-8">
      <div className="mb-4 flex items-center gap-2.5">
        <span className="text-2xl">🤖</span>
        <div>
          <div className="font-display text-base font-bold text-foreground">AI Best Matches For You</div>
          <div className="text-sm text-muted-foreground">
            Based on Dhanmondi area • ৳10K-20K budget • Studio preference
          </div>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {aiPicks.map((r) => (
          <div
            key={r.id}
            className="flex items-center gap-3 rounded-2xl border border-brand/20 bg-linear-to-br from-brand/8 to-brand/4 p-4"
          >
            <img src={r.img} alt={r.name} className="h-15 w-17.5 shrink-0 rounded-lg object-cover" />
            <div>
              <h4 className="font-display text-sm font-bold text-foreground">{r.name}</h4>
              <p className="mb-1.5 text-sm text-muted-foreground">
                ৳{r.price.toLocaleString()}/mo • {r.rating}★ • 94% match
              </p>
              <div className="h-1 overflow-hidden rounded-full bg-muted">
                <div className="h-full rounded-full bg-brand" style={{ width: "94%" }} />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
