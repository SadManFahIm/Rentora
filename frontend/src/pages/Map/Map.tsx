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
    <div className="mx-auto max-w-7xl px-4 py-12 md:px-6 md:py-16 lg:px-8">
      <div className="mb-6 flex items-center justify-between">
        <h2 className="font-display text-xl font-bold text-foreground sm:text-2xl">🗺️ Map View</h2>
        <p className="text-sm text-gray-600 dark:text-gray-400">Browse rooms by location</p>
      </div>

      <div className="mb-6 flex h-100 flex-col items-center justify-center gap-3 rounded-2xl border border-gray-200 bg-linear-to-br from-gray-50 to-gray-200 text-center text-gray-600 dark:border-gray-800 dark:from-gray-800 dark:to-gray-900 dark:text-gray-400">
        <div className="grid grid-cols-8 gap-2 opacity-40">
          {Array(16).fill(0).map((_, i) => (
            <div
              key={i}
              className="h-2 w-2 rounded-full bg-orange-600"
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
            <div key={r.id} className="rounded-lg border border-gray-200 bg-card px-3.5 py-2 text-sm font-semibold dark:border-gray-800">
              📍 {r.area} — ৳{r.price.toLocaleString()}
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {features.map((f) => (
          <div key={f.title} className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
            <div className="mb-2 text-2xl">{f.icon}</div>
            <h4 className="mb-1.5 font-display font-bold text-foreground">{f.title}</h4>
            <p className="text-sm text-gray-600 dark:text-gray-400">{f.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
