import { useState } from "react";
import { useApp } from "../../context/AppContext";
import RoomCard from "../../components/RoomCard/RoomCard";
import RoomModal from "../../components/RoomModal/RoomModal";
import SearchFilter from "../../components/SearchFilter/SearchFilter";
import AIRecommendations from "../../components/AIRecommendations/AIRecommendations";
import type { Room, Filters } from "../../types";

const DEFAULT_FILTERS: Filters = {
  query: "",
  area: "All",
  type: "All",
  sort: "default",
  amenities: [],
  gender: "Any",
  available: "any",
  minPrice: "",
  maxPrice: "",
};

export default function Rooms() {
  const { rooms } = useApp();
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [gridView, setGridView] = useState(true);
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);

  // Apply filters
  const filtered = rooms.filter((r) => {
    if (filters.query && !r.name.toLowerCase().includes(filters.query.toLowerCase()) && !r.area.toLowerCase().includes(filters.query.toLowerCase())) return false;
    if (filters.area !== "All" && r.area !== filters.area) return false;
    if (filters.type !== "All" && r.type !== filters.type) return false;
    if (filters.minPrice && r.price < parseInt(filters.minPrice)) return false;
    if (filters.maxPrice && r.price > parseInt(filters.maxPrice)) return false;
    if (filters.amenities.length && !filters.amenities.every((a) => r.amenities.includes(a))) return false;
    if (filters.gender !== "Any" && r.gender !== "Any" && r.gender !== filters.gender) return false;
    if (filters.available === "yes" && !r.available) return false;
    return true;
  });

  // Sort
  if (filters.sort === "price-asc") filtered.sort((a, b) => a.price - b.price);
  else if (filters.sort === "price-desc") filtered.sort((a, b) => b.price - a.price);
  else if (filters.sort === "rating") filtered.sort((a, b) => b.rating - a.rating);

  return (
    <>
      <SearchFilter filters={filters} setFilters={setFilters} />

      <div className="section-container">
        <div className="section-header">
          <div>
            <h2>Available Rooms</h2>
            <p>{filtered.length} listings found</p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className={`view-btn ${gridView ? "active" : ""}`} onClick={() => setGridView(true)}>⊞</button>
            <button className={`view-btn ${!gridView ? "active" : ""}`} onClick={() => setGridView(false)}>≡</button>
          </div>
        </div>

        <AIRecommendations />

        {filtered.length === 0 ? (
          <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text2)" }}>
            <div style={{ fontSize: "3rem", marginBottom: 16 }}>🔍</div>
            <h3 style={{ fontFamily: "var(--font)", marginBottom: 8 }}>No rooms found</h3>
            <p>Try adjusting your filters</p>
          </div>
        ) : (
          <div className={gridView ? "rooms-grid" : "rooms-list"}>
            {filtered.map((r) => <RoomCard key={r.id} room={r} onClick={setSelectedRoom} />)}
          </div>
        )}
      </div>

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
    </>
  );
}
