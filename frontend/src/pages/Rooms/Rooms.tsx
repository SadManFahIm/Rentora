import { useState } from "react";
import { useRooms } from "../../hooks/useRooms";
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
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [gridView, setGridView] = useState(true);
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);

  // Filtering + sorting happen in the service layer (mock server-side).
  const { data: rooms = [], isLoading } = useRooms(filters);

  return (
    <>
      <SearchFilter filters={filters} setFilters={setFilters} />

      <div className="section-container">
        <div className="section-header">
          <div>
            <h2>Available Rooms</h2>
            <p>{isLoading ? "Loading…" : `${rooms.length} listings found`}</p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className={`view-btn ${gridView ? "active" : ""}`} onClick={() => setGridView(true)}>⊞</button>
            <button className={`view-btn ${!gridView ? "active" : ""}`} onClick={() => setGridView(false)}>≡</button>
          </div>
        </div>

        <AIRecommendations />

        {isLoading ? (
          <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text2)" }}>
            <div style={{ fontSize: "3rem", marginBottom: 16 }}>⏳</div>
            <h3 style={{ fontFamily: "var(--font)", marginBottom: 8 }}>Loading rooms…</h3>
          </div>
        ) : rooms.length === 0 ? (
          <div style={{ textAlign: "center", padding: "60px 20px", color: "var(--text2)" }}>
            <div style={{ fontSize: "3rem", marginBottom: 16 }}>🔍</div>
            <h3 style={{ fontFamily: "var(--font)", marginBottom: 8 }}>No rooms found</h3>
            <p>Try adjusting your filters</p>
          </div>
        ) : (
          <div className={gridView ? "rooms-grid" : "rooms-list"}>
            {rooms.map((r) => <RoomCard key={r.id} room={r} onClick={setSelectedRoom} />)}
          </div>
        )}
      </div>

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
    </>
  );
}
