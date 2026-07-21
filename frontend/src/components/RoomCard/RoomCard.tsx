import { useWishlistStore } from "../../stores/wishlistStore";
import type { Room, RoomType } from "../../types";
import "./RoomCard.css";

interface RoomCardProps {
  room: Room;
  onClick: (room: Room) => void;
}

export default function RoomCard({ room, onClick }: RoomCardProps) {
  const wishlist = useWishlistStore((s) => s.wishlist);
  const toggleWishlist = useWishlistStore((s) => s.toggleWishlist);
  const isWishlisted = wishlist.includes(room.id);
  const typeClasses: Record<RoomType, string> = {
    Single: "tag-single",
    Shared: "tag-shared",
    Studio: "tag-studio",
  };
  const typeClass = typeClasses[room.type] || "";

  return (
    <div className="room-card fade-in" onClick={() => onClick(room)}>
      {/* Image */}
      <div className="room-card-img">
        <img src={room.img} alt={room.name} loading="lazy" />
        <span className={`room-badge ${!room.available ? "unavailable" : ""}`}>
          {room.available ? room.type : "Unavailable"}
        </span>
        <button
          className="wishlist-btn"
          onClick={(e) => { e.stopPropagation(); toggleWishlist(room.id); }}
        >
          {isWishlisted ? "❤️" : "🤍"}
        </button>
      </div>

      {/* Body */}
      <div className="room-card-body">
        <div className="room-meta">
          <div>
            <div className="room-name">{room.name}</div>
            <div className="room-loc">📍 {room.area}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="room-price">
              ৳{room.price.toLocaleString()}<sub>/mo</sub>
            </div>
            <span className={`tag-pill ${typeClass}`}>{room.type}</span>
          </div>
        </div>

        {/* Amenities */}
        <div className="room-amenities">
          {room.amenities.slice(0, 3).map((a) => (
            <span key={a} className="amenity-tag">{a}</span>
          ))}
          {room.amenities.length > 3 && (
            <span className="amenity-tag">+{room.amenities.length - 3}</span>
          )}
        </div>

        {/* Footer */}
        <div className="room-footer">
          <div className="room-rating">
            ⭐ {room.rating}
            <span style={{ color: "var(--text2)", fontWeight: 400, marginLeft: 2 }}>
              ({room.reviews})
            </span>
          </div>
          <div className="room-owner">
            <div className="owner-avatar">{room.ownerAvatar}</div>
            {room.owner}
            {room.verified && <span className="verified-badge">✓</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
