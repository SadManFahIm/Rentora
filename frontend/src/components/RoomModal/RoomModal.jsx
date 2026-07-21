import "./RoomModal.css";

const amenityEmoji = { WiFi: "📶", AC: "❄️", "Attached Bath": "🚿", Furnished: "🛋️", Gym: "💪", Parking: "🚗" };

export default function RoomModal({ room, onClose }) {
  if (!room) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <img src={room.img} alt={room.name} className="modal-img" />
        <div className="modal-body">

          {/* Header */}
          <div className="modal-header">
            <div>
              <h2 className="modal-title">{room.name}</h2>
              <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 4 }}>
                <span className="stars">{"★".repeat(Math.floor(room.rating))} {room.rating}</span>
                <span style={{ color: "var(--text2)", fontSize: "0.82rem" }}>({room.reviews} reviews)</span>
                {room.verified && <span className="verified-badge">✓ KYC Verified</span>}
              </div>
            </div>
            <button className="close-btn" onClick={onClose}>✕</button>
          </div>

          {/* Price */}
          <div className="modal-price">
            ৳{room.price.toLocaleString()}
            <span className="modal-price-sub">/month</span>
          </div>
          <div className="price-insight">
            🤖 AI Price Insight: This listing is <strong>8% below market average</strong> for {room.area}. Great deal!
          </div>

          {/* Info Grid */}
          <div className="modal-info-grid">
            <div className="info-box"><strong>{room.type}</strong><span>Room Type</span></div>
            <div className="info-box"><strong>{room.size} sqft</strong><span>Size</span></div>
            <div className="info-box"><strong>{room.gender}</strong><span>Gender Pref.</span></div>
          </div>

          {/* Description */}
          <p className="modal-desc">{room.description}</p>

          {/* Amenities */}
          <div className="modal-amenities">
            {room.amenities.map((a) => (
              <span key={a} className="amenity-full">
                {amenityEmoji[a] || "✓"} {a}
              </span>
            ))}
          </div>

          {/* Owner */}
          <div className="modal-owner">
            <div className="owner-avatar" style={{ width: 40, height: 40, fontSize: "0.85rem" }}>
              {room.ownerAvatar}
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>{room.owner}</div>
              {room.verified && <span className="verified-badge">✓ NID Verified</span>}
            </div>
          </div>

          {/* Actions */}
          <div className="modal-actions">
            <button className="btn-outline">💬 Message Owner</button>
            <button className="btn-primary">📅 Book Now</button>
          </div>
        </div>
      </div>
    </div>
  );
}
