// ============================================================
// SHARED TYPES — domain models used across the app
// ============================================================

export type RoomType = "Single" | "Shared" | "Studio";
export type GenderPref = "Any" | "Male" | "Female";

export type LandmarkKind = "university" | "metro";

/** A single nearby landmark with its distance from a room (Phase 7 geo). */
export interface LandmarkProximity {
  key: string;
  name: string;
  kind: LandmarkKind;
  distanceKm: number;
}

/** Nearest university/metro to a room, as returned by the backend. */
export interface RoomProximity {
  nearestUniversity: LandmarkProximity | null;
  nearestMetro: LandmarkProximity | null;
}

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
  ownerId: number | null;
  ownerAvatar: string;
  verified: boolean;
  /** Nearest university/metro (present when the API includes it). */
  proximity?: RoomProximity;
  /** Distance (km) from a geo query's reference point; null unless the request supplied one. */
  distanceKm?: number | null;
}

export type UserRole = "tenant" | "landlord" | "admin";

export interface User {
  id?: number;
  name: string;
  email: string;
  username?: string;
  firstName?: string;
  lastName?: string;
  role?: UserRole;
  avatar?: string | null;
  phone?: string;
  bio?: string;
  nidVerified?: boolean;
}

export interface Notification {
  id: number;
  text: string;
  read: boolean;
  time: string;
}

// ---- Chat (real-time, backed by chat/ REST + WebSocket) ----
export interface ChatUser {
  id: number;
  username: string;
  firstName: string;
  lastName: string;
  avatar: string | null;
}

export type ChatMessageType = "text" | "image" | "file" | "system";
export type ChatMessageStatus = "sent" | "delivered" | "read";

export interface ChatMessage {
  id: number;
  chatRoomId: number;
  sender: ChatUser;
  content: string;
  messageType: ChatMessageType;
  fileUrl: string;
  status: ChatMessageStatus;
  createdAt: string;
}

export type ChatRoomType = "direct" | "group";

export interface ChatRoom {
  id: number;
  roomType: ChatRoomType;
  listingId: number | null;
  listingTitle: string | null;
  participants: ChatUser[];
  otherParticipant: ChatUser | null;
  isOtherUserOnline: boolean | null;
  lastMessage: ChatMessage | null;
  unreadCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface Review {
  name: string;
  avatar: string;
  rating: number;
  text: string;
  date: string;
}

export type BookingStatus = "approved" | "pending" | "rejected" | "cancelled";

export interface Booking extends Room {
  bookingId: number;
  status: BookingStatus;
  date: string;
  checkIn: string;
  monthlyRent: number;
  securityDepositAmount: number;
  securityDepositPaid: boolean;
  securityDepositRefunded: boolean;
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

// Filters as sent to the service layer — every field optional.
export type RoomFilters = Partial<Filters>;

// ---- API payloads ----
export type CreateRoomPayload = Omit<Room, "id" | "rating" | "reviews">;
export type UpdateRoomPayload = Partial<CreateRoomPayload>;

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
}

export interface AuthResult {
  user: User;
  access: string;
  refresh: string;
}

export interface CreateBookingPayload {
  roomId: number;
  /** ISO date (YYYY-MM-DD) for check-in. */
  checkIn: string;
}

export interface DashboardLandlordStats {
  total_listings: number;
  total_bookings_received: number;
  avg_rating: number;
  total_revenue: number;
}

export interface DashboardStats {
  saved_rooms_count: number;
  active_bookings: number;
  pending_bookings: number;
  total_reviews_given: number;
  unread_notifications: number;
  profile_completion: number;
  landlord?: DashboardLandlordStats;
}

// ---- Payments (Phase 5) ----

/** Gateways a payment can actually be *initiated* through from the UI. */
export type PaymentGateway = "sslcommerz" | "bkash";

export type PaymentMethod = PaymentGateway | "nagad" | "manual";

export type PaymentType = "booking_deposit" | "monthly_rent" | "security_deposit";

export type PaymentStatus =
  | "initiated"
  | "pending"
  | "success"
  | "failed"
  | "cancelled"
  | "refunded";

export interface Payment {
  id: number;
  bookingId: number;
  amount: number;
  method: PaymentMethod;
  type: PaymentType;
  status: PaymentStatus;
  transactionId: string;
  gatewayTransactionId: string;
  failureReason: string;
  createdAt: string;
  updatedAt: string;
}

/** Filters as sent to the service layer — every field optional. */
export interface PaymentFilters {
  status?: PaymentStatus;
  method?: PaymentMethod;
  type?: PaymentType;
  /** ISO date (YYYY-MM-DD). */
  dateFrom?: string;
  /** ISO date (YYYY-MM-DD). */
  dateTo?: string;
}

export interface PaymentSummary {
  totalPaid: number;
  totalPending: number;
  totalRefunded: number;
  countPaid: number;
  countPending: number;
  countRefunded: number;
}

export interface DepositStatus {
  bookingId: number;
  securityDepositAmount: number;
  securityDepositPaid: boolean;
  securityDepositRefunded: boolean;
  requiredBeforeApproval: boolean;
}

export interface InitiatePaymentResult {
  paymentUrl: string;
  transactionId: string;
}

/** The outcome the backend redirects the browser back with after a gateway callback. */
export type PaymentOutcome = "success" | "fail" | "cancel";
