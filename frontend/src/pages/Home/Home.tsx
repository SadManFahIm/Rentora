import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRooms } from "../../hooks/useRooms";
import RoomCard from "../../components/RoomCard/RoomCard";
import RoomModal from "../../components/RoomModal/RoomModal";
import AIRecommendations from "../../components/AIRecommendations/AIRecommendations";
import { mockReviews } from "../../data/mockData";
import type { Room } from "../../types";
import "./Home.css";

interface AIFeature {
  icon: string;
  title: string;
  desc: string;
}

function HeroSection() {
  const navigate = useNavigate();
  return (
    <div className="hero">
      <div className="hero-content">
        <div className="hero-badge"><span className="hero-badge-dot"></span> 2,400+ Verified Listings in Dhaka</div>
        <h1>Find Your Perfect <em>Room</em> in Bangladesh</h1>
        <p>AI-powered room search with verified landlords, secure payments, and real-time availability. The smarter way to rent in 2025.</p>
        <div className="hero-search">
          <input placeholder="Search area, room type..." />
          <button className="btn-primary" onClick={() => navigate("/rooms")}>Search Rooms</button>
        </div>
        <div className="hero-stats">
          <div className="hero-stat"><strong>2.4K+</strong><span>Active Listings</span></div>
          <div className="hero-stat"><strong>98%</strong><span>Verified Owners</span></div>
          <div className="hero-stat"><strong>4.8★</strong><span>Avg Rating</span></div>
        </div>
      </div>
      <div className="hero-visual">
        <div className="hero-img-grid">
          <div className="hero-img hero-img-full"><img src="https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=600&q=80" alt="Room" /></div>
          <div className="hero-img"><img src="https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=400&q=80" alt="Room" /></div>
          <div className="hero-img"><img src="https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=400&q=80" alt="Room" /></div>
        </div>
        <div className="floating-card floating-tl">
          <span className="floating-icon">🛡️</span>
          <div><div className="floating-title">KYC Verified</div><div className="floating-sub">All landlords checked</div></div>
        </div>
        <div className="floating-card floating-br">
          <span className="floating-icon">⚡</span>
          <div><div className="floating-title">Instant Booking</div><div className="floating-sub">Book in 2 minutes</div></div>
        </div>
      </div>
    </div>
  );
}

function AISection() {
  const features: AIFeature[] = [
    { icon: "🎯", title: "Smart Recommendations", desc: "Personalized room suggestions based on your budget, location history and preferences." },
    { icon: "✍️", title: "AI Description Generator", desc: "Auto-generate professional listing descriptions with grammar correction." },
    { icon: "🛡️", title: "Fraud Detection", desc: "Detects duplicate listings, suspicious pricing, and fake images automatically." },
    { icon: "📈", title: "Price Prediction", desc: "Get optimal rent price suggestions based on market trends and area data." },
  ];
  return (
    <div className="ai-section">
      <div className="ai-inner">
        <div className="ai-label">✨ AI-Powered</div>
        <h2>Smarter Renting with<br />Artificial Intelligence</h2>
        <p>Our AI engine analyzes thousands of listings to give you the best recommendations, detect fraud, and predict fair market prices.</p>
        <div className="ai-features-grid">
          {features.map((f) => (
            <div key={f.title} className="ai-feature">
              <div className="ai-feature-icon">{f.icon}</div>
              <h4>{f.title}</h4>
              <p>{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ReviewSection() {
  return (
    <div className="section-container">
      <h2 style={{ fontFamily: "var(--font)", fontSize: "1.6rem", fontWeight: 800, marginBottom: 24 }}>What Tenants Say ⭐</h2>
      <div className="reviews-grid">
        {mockReviews.map((r) => (
          <div key={r.name} className="review-card">
            <div className="review-header">
              <div className="reviewer">
                <div className="owner-avatar" style={{ width: 40, height: 40 }}>{r.avatar}</div>
                <div>
                  <div className="reviewer-name">{r.name}</div>
                  <div className="reviewer-date">{r.date}</div>
                </div>
              </div>
              <span className="stars">{"★".repeat(r.rating)} {r.rating}</span>
            </div>
            <p className="review-text">{r.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Home() {
  const { data: rooms = [] } = useRooms();
  const navigate = useNavigate();
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const featured = rooms.filter((r) => r.featured);

  return (
    <>
      <HeroSection />
      <AIRecommendations />

      {/* Featured Rooms */}
      <div className="section-container">
        <div className="section-header">
          <div><h2>Featured Rooms</h2><p>Hand-picked by our team</p></div>
          <button className="btn-outline" onClick={() => navigate("/rooms")}>View All →</button>
        </div>
        <div className="rooms-grid">
          {featured.map((r) => <RoomCard key={r.id} room={r} onClick={setSelectedRoom} />)}
        </div>
      </div>

      <AISection />
      <ReviewSection />

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
    </>
  );
}
