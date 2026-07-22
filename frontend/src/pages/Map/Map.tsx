// Map Page
import { useRooms } from "../../hooks/useRooms";

interface MapFeature {
  icon: string;
  title: string;
  desc: string;
}

export default function Map() {
  const { data: rooms = [] } = useRooms();

  const features: MapFeature[] = [
    { icon: "🏫", title: "Near Universities", desc: "Rooms within 1km of DU, BUET, NSU" },
    { icon: "🚇", title: "Metro Access", desc: "Filter by proximity to MRT-6 stations" },
    { icon: "🔥", title: "Price Heatmap", desc: "Visualize rent distribution across Dhaka" },
  ];

  return (
    <div className="mx-auto max-w-300 px-4 py-8 sm:px-8">
      <div className="mb-6 flex items-center justify-between">
        <h2 className="font-display text-xl font-bold text-foreground sm:text-2xl">🗺️ Map View</h2>
        <p className="text-sm text-muted-foreground">Browse rooms by location</p>
      </div>

      <div className="mb-6 flex h-100 flex-col items-center justify-center gap-3 rounded-2xl border border-border bg-linear-to-br from-muted to-border text-center text-muted-foreground">
        <div className="grid grid-cols-8 gap-2 opacity-40">
          {Array(16).fill(0).map((_, i) => (
            <div
              key={i}
              className="h-2 w-2 rounded-full bg-brand"
              style={{ opacity: i % 3 === 0 ? 1 : 0.3 }}
            />
          ))}
        </div>
        <h3 className="font-display text-lg font-bold text-foreground">Interactive Map</h3>
        <p className="text-sm">
          OpenStreetMap integration — showing {rooms.filter((r) => r.available).length} available listings
        </p>
        <div className="mt-2 flex flex-wrap justify-center gap-2.5 px-4">
          {rooms.filter((r) => r.available).map((r) => (
            <div key={r.id} className="rounded-lg border border-border bg-card px-3.5 py-2 text-sm font-semibold">
              📍 {r.area} — ৳{r.price.toLocaleString()}
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {features.map((f) => (
          <div key={f.title} className="rounded-2xl border border-border bg-card p-5">
            <div className="mb-2 text-2xl">{f.icon}</div>
            <h4 className="mb-1.5 font-display font-bold text-foreground">{f.title}</h4>
            <p className="text-sm text-muted-foreground">{f.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
