// ============================================================
// SHARED TYPES — domain models used across the app
// ============================================================

export type RoomType = "Single" | "Shared" | "Studio";
export type GenderPref = "Any" | "Male" | "Female";

export interface Room {
  id: number;
  name: string;
  type: RoomType;
  price: number;
  area: string;
  lat: number;
  lng: number;
  rating: number;
  reviews: number;
  img: string;
  amenities: string[];
  gender: GenderPref;
  available: boolean;
  featured: boolean;
  description: string;
  size: number;
  owner: string;
  ownerAvatar: string;
  verified: boolean;
}

export interface User {
  name: string;
  email: string;
}

export interface Notification {
  id: number;
  text: string;
  read: boolean;
  time: string;
}

export interface Message {
  id: number;
  from: string;
  avatar: string;
  text: string;
  time: string;
  mine: boolean;
}

export interface Review {
  name: string;
  avatar: string;
  rating: number;
  text: string;
  date: string;
}

export type BookingStatus = "approved" | "pending" | "rejected";

export interface Booking extends Room {
  status: BookingStatus;
  date: string;
}

// ---- Search / filter state ----
export type SortOption = "default" | "price-asc" | "price-desc" | "rating";
export type AvailabilityFilter = "any" | "yes";

export interface Filters {
  query: string;
  area: string;
  type: string;
  sort: SortOption;
  amenities: string[];
  gender: GenderPref;
  available: AvailabilityFilter;
  minPrice: string;
  maxPrice: string;
}
