import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRooms } from "../../hooks/useRooms";
import RoomCard from "../../components/RoomCard/RoomCard";
import RoomCardSkeleton from "../../components/RoomCardSkeleton";
import RoomModal from "../../components/RoomModal/RoomModal";
import AIRecommendations from "../../components/AIRecommendations/AIRecommendations";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { mockReviews } from "../../data/mockData";
import type { Room } from "../../types";

interface AIFeature {
  icon: string;
  title: string;
  desc: string;
}

function HeroSection() {
  const navigate = useNavigate();
  return (
    <div className="mx-auto grid max-w-7xl grid-cols-1 items-center gap-10 px-4 py-12 md:gap-16 md:px-6 md:py-16 lg:grid-cols-2 lg:px-8">
      <div>
        <div className="mb-5 inline-flex items-center gap-2 rounded-full bg-orange-50 px-3.5 py-1.5 text-sm font-semibold text-orange-600 dark:bg-orange-950/40 dark:text-orange-400">
          <span className="h-2 w-2 animate-pulse rounded-full bg-orange-600" /> 2,400+ Verified Listings in Dhaka
        </div>
        <h1 className="mb-4 font-display text-[clamp(2.2rem,4vw,3.2rem)] font-bold leading-[1.15] tracking-tight text-foreground">
          Find Your Perfect <em className="not-italic text-orange-600 dark:text-orange-400">Room</em> in Bangladesh
        </h1>
        <p className="mb-8 text-base leading-relaxed text-gray-600 dark:text-gray-400 sm:text-lg">
          AI-powered room search with verified landlords, secure payments, and real-time availability. The smarter way to rent in 2025.
        </p>
        <div className="flex gap-2 rounded-2xl border border-gray-200 bg-card p-2 shadow-sm dark:border-gray-800">
          <Input
            className="h-11 border-none bg-transparent shadow-none focus-visible:ring-0"
            placeholder="Search area, room type..."
          />
          <Button className="h-11 shrink-0 bg-orange-600 text-white hover:bg-orange-700" onClick={() => navigate("/rooms")}>
            Search Rooms
          </Button>
        </div>
        <div className="mt-6 flex gap-8">
          <div className="flex flex-col">
            <strong className="font-display text-2xl font-bold text-foreground">2.4K+</strong>
            <span className="text-sm text-gray-600 dark:text-gray-400">Active Listings</span>
          </div>
          <div className="flex flex-col">
            <strong className="font-display text-2xl font-bold text-foreground">98%</strong>
            <span className="text-sm text-gray-600 dark:text-gray-400">Verified Owners</span>
          </div>
          <div className="flex flex-col">
            <strong className="font-display text-2xl font-bold text-foreground">4.8★</strong>
            <span className="text-sm text-gray-600 dark:text-gray-400">Avg Rating</span>
          </div>
        </div>
      </div>
      <div className="relative hidden lg:block">
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2 overflow-hidden rounded-2xl">
            <img
              src="https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?w=600&q=80"
              alt="Room"
              className="h-60 w-full object-cover transition-transform duration-400 hover:scale-105"
            />
          </div>
          <div className="overflow-hidden rounded-2xl">
            <img
              src="https://images.unsplash.com/photo-1522708323590-d24dbb6b0267?w=400&q=80"
              alt="Room"
              className="h-45 w-full object-cover transition-transform duration-400 hover:scale-105"
            />
          </div>
          <div className="overflow-hidden rounded-2xl">
            <img
              src="https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=400&q=80"
              alt="Room"
              className="h-45 w-full object-cover transition-transform duration-400 hover:scale-105"
            />
          </div>
        </div>
        <div className="absolute -left-4 -top-4 flex items-center gap-2.5 rounded-2xl border border-gray-200 bg-card px-4 py-3 text-sm font-semibold shadow-lg dark:border-gray-800">
          <span className="text-2xl">🛡️</span>
          <div>
            <div className="font-bold text-foreground">KYC Verified</div>
            <div className="text-xs text-gray-600 dark:text-gray-400">All landlords checked</div>
          </div>
        </div>
        <div className="absolute -right-4 bottom-15 flex items-center gap-2.5 rounded-2xl border border-gray-200 bg-card px-4 py-3 text-sm font-semibold shadow-lg dark:border-gray-800">
          <span className="text-2xl">⚡</span>
          <div>
            <div className="font-bold text-foreground">Instant Booking</div>
            <div className="text-xs text-gray-600 dark:text-gray-400">Book in 2 minutes</div>
          </div>
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
    <div className="my-10 bg-gray-900 px-4 py-12 text-white md:px-6 md:py-16 lg:px-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-5 inline-flex items-center gap-2 rounded-full bg-orange-600/30 px-3.5 py-1.5 text-sm font-semibold text-orange-400">
          ✨ AI-Powered
        </div>
        <h2 className="mb-3 font-display text-2xl font-bold leading-tight sm:text-3xl">
          Smarter Renting with
          <br />
          Artificial Intelligence
        </h2>
        <p className="mb-8 leading-relaxed text-white/70">
          Our AI engine analyzes thousands of listings to give you the best recommendations, detect fraud, and predict fair market prices.
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-2xl border border-white/10 bg-white/5 p-5 transition-colors hover:border-orange-600/30 hover:bg-orange-600/15"
            >
              <div className="mb-2.5 text-3xl">{f.icon}</div>
              <h4 className="mb-1.5 font-display text-sm font-bold">{f.title}</h4>
              <p className="text-sm leading-relaxed text-white/60">{f.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ReviewSection() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-12 md:px-6 md:py-16 lg:px-8">
      <h2 className="mb-6 font-display text-xl font-bold text-foreground sm:text-2xl">What Tenants Say ⭐</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {mockReviews.map((r) => (
          <div key={r.name} className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
            <div className="mb-2.5 flex items-start justify-between">
              <div className="flex items-center gap-2.5">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-orange-600 text-xs font-bold text-white">
                  {r.avatar}
                </div>
                <div>
                  <div className="text-sm font-semibold text-foreground">{r.name}</div>
                  <div className="text-xs text-gray-600 dark:text-gray-400">{r.date}</div>
                </div>
              </div>
              <span className="text-sm font-semibold text-amber-500">{"★".repeat(r.rating)} {r.rating}</span>
            </div>
            <p className="text-sm leading-relaxed text-gray-600 dark:text-gray-400">{r.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Home() {
  const { data: rooms = [], isLoading } = useRooms();
  const navigate = useNavigate();
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const featured = rooms.filter((r) => r.featured);

  return (
    <>
      <HeroSection />
      <AIRecommendations />

      {/* Featured Rooms */}
      <div className="mx-auto max-w-7xl px-4 py-12 md:px-6 md:py-16 lg:px-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="font-display text-xl font-bold text-foreground sm:text-2xl">Featured Rooms</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">Hand-picked by our team</p>
          </div>
          <Button variant="outline" onClick={() => navigate("/rooms")}>
            View All →
          </Button>
        </div>
        {isLoading ? (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <RoomCardSkeleton key={i} />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {featured.map((r) => (
              <RoomCard key={r.id} room={r} onClick={setSelectedRoom} />
            ))}
          </div>
        )}
      </div>

      <AISection />
      <ReviewSection />

      {selectedRoom && <RoomModal room={selectedRoom} onClose={() => setSelectedRoom(null)} />}
    </>
  );
}
