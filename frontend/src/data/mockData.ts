// ============================================================
// MOCK DATA — content still awaiting a real backend source
// (reviews aren't wired to an API yet; the filter option lists
// mirror the backend's fixed choices).
// ============================================================

import type { Review } from "../types";

export const mockReviews: Review[] = [
  {
    name: "Tahmina Akter",
    avatar: "TA",
    rating: 5,
    text: "Found my perfect studio in Dhanmondi within a week! The KYC verification gave me confidence.",
    date: "Jan 2025",
  },
  {
    name: "Mehedi Hasan",
    avatar: "MH",
    rating: 4,
    text: "The AI price suggestion saved me ৳2,000/month. Showed me the market average.",
    date: "Jan 2025",
  },
  {
    name: "Priya Sen",
    avatar: "PS",
    rating: 5,
    text: "Chat feature made communication with the landlord so easy. Booked without multiple visits!",
    date: "Dec 2024",
  },
];

export const AREAS: string[] = [
  "All",
  "Dhanmondi",
  "Mirpur",
  "Gulshan",
  "Banani",
  "Mohammadpur",
  "Azimpur",
];
export const ROOM_TYPES: string[] = ["All", "Single", "Shared", "Studio"];
export const AMENITIES_LIST: string[] = [
  "WiFi",
  "AC",
  "Attached Bath",
  "Furnished",
  "Gym",
  "Parking",
];
