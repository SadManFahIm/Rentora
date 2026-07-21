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
    <div className="section-container">
      <div className="section-header">
        <h2>🗺️ Map View</h2>
        <p>Browse rooms by location</p>
      </div>
      <div className="map-placeholder">
        <div className="map-dots">
          {Array(16).fill(0).map((_, i) => (
            <div key={i} className="map-dot" style={{ opacity: i % 3 === 0 ? 1 : 0.3 }} />
          ))}
        </div>
        <h3>Interactive Map</h3>
        <p>OpenStreetMap integration — showing {rooms.filter((r) => r.available).length} available listings</p>
        <div className="map-markers">
          {rooms.filter((r) => r.available).map((r) => (
            <div key={r.id} className="map-marker">
              📍 {r.area} — ৳{r.price.toLocaleString()}
            </div>
          ))}
        </div>
      </div>
      <div className="map-features">
        {features.map((f) => (
          <div key={f.title} className="map-feature-card">
            <div className="mfc-icon">{f.icon}</div>
            <h4>{f.title}</h4>
            <p>{f.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
