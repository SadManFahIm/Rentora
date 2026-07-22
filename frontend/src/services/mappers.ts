// ============================================================
// MAPPERS — translate Django/DRF payloads into frontend domain
// types. Keeps every field-name / shape difference in one place.
// ============================================================

import type {
  Room,
  RoomType,
  GenderPref,
  Booking,
  BookingStatus,
  Notification,
  User,
} from "../types";

// ---- DRF wire shapes (only the fields we consume) ----

/** DRF PageNumberPagination envelope. */
export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ApiRoomImage {
  id: number;
  image: string;
  is_primary: boolean;
  created_at: string;
}

export interface ApiOwner {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  avatar: string | null;
  phone: string;
  nid_verified: boolean;
}

export interface ApiRoom {
  id: number;
  title: string;
  description?: string;
  room_type: string;
  price: string | number;
  area: string;
  lat?: string | number;
  lng?: string | number;
  amenities?: string[];
  gender_preference: string;
  size_sqft: number;
  is_available: boolean;
  is_featured: boolean;
  rating: string | number;
  total_reviews: number;
  verified: boolean;
  owner?: ApiOwner | null;
  images?: ApiRoomImage[];
  created_at: string;
}

export interface ApiBooking {
  id: number;
  room: ApiRoom;
  status: BookingStatus;
  check_in: string;
  check_out: string | null;
  monthly_rent: string | number;
  agreement_signed: boolean;
  notes: string;
  created_at: string;
}

export interface ApiNotification {
  id: number;
  notification_type: string;
  notification_type_display: string;
  title: string;
  message: string;
  is_read: boolean;
  action_url: string;
  created_at: string;
}

export interface ApiUser {
  pk?: number;
  id?: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  phone?: string;
  avatar?: string | null;
  role?: string;
  gender?: string;
  nid_verified?: boolean;
  bio?: string;
  date_of_birth?: string | null;
}

// ---- helpers ----

const capitalize = (s: string): string =>
  s ? s.charAt(0).toUpperCase() + s.slice(1) : s;

const roomTypeLabel = (value: string): RoomType =>
  capitalize(value) as RoomType;

const genderLabel = (value: string): GenderPref => capitalize(value) as GenderPref;

const FALLBACK_IMAGE = (id: number): string =>
  `https://picsum.photos/seed/rentora-room-${id}/600/400`;

function pickImage(room: ApiRoom): string {
  const images = room.images ?? [];
  if (images.length === 0) return FALLBACK_IMAGE(room.id);
  const primary = images.find((img) => img.is_primary) ?? images[0];
  return primary.image;
}

function ownerName(owner: ApiOwner | null | undefined): string {
  if (!owner) return "Owner";
  const full = [owner.first_name, owner.last_name].filter(Boolean).join(" ").trim();
  return full || owner.username;
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Human-friendly relative time (e.g. "2h ago") from an ISO timestamp. */
export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.floor((Date.now() - then) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// ---- mappers ----

export function mapRoom(api: ApiRoom): Room {
  const owner = ownerName(api.owner);
  return {
    id: api.id,
    name: api.title,
    type: roomTypeLabel(api.room_type),
    price: Number(api.price),
    area: api.area,
    lat: Number(api.lat ?? 0),
    lng: Number(api.lng ?? 0),
    rating: Number(api.rating),
    reviews: api.total_reviews,
    img: pickImage(api),
    amenities: api.amenities ?? [],
    gender: genderLabel(api.gender_preference),
    available: api.is_available,
    featured: api.is_featured,
    description: api.description ?? "",
    size: api.size_sqft,
    owner,
    ownerAvatar: initials(owner),
    verified: api.verified,
  };
}

export function mapBooking(api: ApiBooking): Booking {
  return {
    ...mapRoom(api.room),
    bookingId: api.id,
    status: api.status,
    date: formatDate(api.check_in),
    checkIn: api.check_in,
    monthlyRent: Number(api.monthly_rent),
  };
}

export function mapNotification(api: ApiNotification): Notification {
  return {
    id: api.id,
    text: api.message || api.title,
    read: api.is_read,
    time: relativeTime(api.created_at),
  };
}

export function mapUser(api: ApiUser): User {
  const full = [api.first_name, api.last_name].filter(Boolean).join(" ").trim();
  return {
    id: api.pk ?? api.id,
    name: full || api.username || api.email,
    email: api.email,
    username: api.username,
    firstName: api.first_name,
    lastName: api.last_name,
    role: api.role as User["role"],
    avatar: api.avatar ?? null,
    phone: api.phone,
    bio: api.bio,
    nidVerified: api.nid_verified,
  };
}
