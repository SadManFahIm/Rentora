// ============================================================
// SHARED TYPES — domain models used across the app
// ============================================================

export type RoomType = "Single" | "Shared" | "Studio";
export type GenderPref = "Any" | "Male" | "Female";

/** Paid listing tier (monetization): free is the default; featured/premium
 * are unlocked via a promotion payment and expire. */
export type ListingTier = "free" | "featured" | "premium";

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
  tier: ListingTier;
  tierExpiresAt: string | null;
  description: string;
  size: number;
  owner: string;
  ownerId: number | null;
  ownerAvatar: string;
  verified: boolean;
  /** Distance (km) from the query's reference point — set on radius/map queries. */
  distanceKm?: number | null;
  /** Nearest university + metro to this listing, each with distance in km. */
  proximity?: {
    nearestUniversity: { key: string; name: string; distanceKm: number } | null;
    nearestMetro: { key: string; name: string; distanceKm: number } | null;
  } | null;
}

/** Public tier catalog from GET /rooms/tier-catalog/. */
export interface TierInfo {
  tier: ListingTier;
  label: string;
  price: number;
  benefits: string[];
}

export interface TierCatalog {
  tiers: TierInfo[];
  durationDays: number;
  currency: string;
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
  /** Django staff — treated as admin in the UI (mirrors the backend check). */
  isStaff?: boolean;
  avatar?: string | null;
  phone?: string;
  bio?: string;
  nidVerified?: boolean;
  /** Email-OTP two-factor authentication is enabled for this account. */
  otpEnabled?: boolean;
  /** Registered WebAuthn passkeys (from the user detail payload). */
  passkeys?: PasskeyInfo[];
}

export interface PasskeyInfo {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
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
  /** KYC-verified — shown as a trust badge next to the participant's name. */
  nidVerified?: boolean;
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
  /** KYC-verified landlords only (Room.verified). */
  verified: boolean;
  /** AI smart search toggle: semantic ranking + natural-language parsing. */
  smart?: boolean;
}

// Filters as sent to the service layer — every field optional.
export type RoomFilters = Partial<Filters> & {
  owner?: number;
  /** Map viewport, GeoJSON order: minLng,minLat,maxLng,maxLat. */
  bbox?: string;
  /** Reference-point latitude (pair with nearLng). */
  nearLat?: number;
  /** Reference-point longitude (pair with nearLat). */
  nearLng?: number;
  /** Keep only rooms within this many km of the reference point. */
  radiusKm?: number;
  /** AI smart search: semantic ranking + natural-language parsing. */
  smart?: boolean;
};

/** What the backend understood from a natural-language query (`smart=1`). */
export interface NlParsed {
  budget_max: number | null;
  areas: string[];
  room_type: string | null;
  gender: string | null;
  months: string[];
  /** Human-readable chips, e.g. "Budget ≤ ৳10,000 · Uttara". */
  hints: string[];
}

/** A room surfaced by the image-similarity endpoint. */
export interface SimilarImageResult extends Room {
  phash_distance: number;
}

/** A university or metro station from GET /rooms/landmarks/. */
export interface Landmark {
  key: string;
  name: string;
  kind: "university" | "metro";
  lat: number;
  lng: number;
}

/** A place suggestion from the map's street-search autocomplete. */
export interface GeocodeSuggestion {
  key: string;
  label: string;
  kind: "street" | "area" | "university" | "metro";
  lat: number;
  lng: number;
}

/** Aggregate room counts from GET /rooms/summary/ (map badge + area chips). */
export interface MapSummary {
  total: number;
  available: number;
  avg_price: number | null;
  min_price: number | null;
  max_price: number | null;
  by_area: {
    area: string;
    count: number;
    /** Fly-to point for the area chip, when the gazetteer knows the area. */
    lat?: number;
    lng?: number;
  }[];
}

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
  /** Optional referral code that attributed this signup (Phase 10). */
  ref?: string;
}

export interface AuthResult {
  user: User;
  access: string;
  refresh: string;
}

/** Response from login when the account has email-OTP 2FA enabled. */
export interface OtpPending {
  otpRequired: true;
  challenge: string;
  destinationMasked: string;
  expiresIn: number;
  user: User;
}

/** Login either completes with JWTs or demands a one-time code. */
export type LoginResult = AuthResult | OtpPending;

export function isOtpPending(result: LoginResult): result is OtpPending {
  return "otpRequired" in result && result.otpRequired === true;
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

export type PaymentType =
  "booking_deposit" | "monthly_rent" | "security_deposit" | "listing_feature" | "listing_premium";

export type PaymentStatus =
  "initiated" | "pending" | "success" | "failed" | "cancelled" | "refunded";

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

// ---- Roommate matching (Phase: roommate matching) ----

export type LifestyleTag =
  | "early_bird"
  | "night_owl"
  | "non_smoker"
  | "smoker"
  | "student"
  | "working_professional"
  | "quiet"
  | "social"
  | "veggie"
  | "pet_friendly"
  | "clean"
  | "guest_friendly";

export interface RoommateProfile {
  id: number;
  username: string;
  budgetMin: number;
  budgetMax: number;
  preferredArea: string;
  roomTypePref: string;
  genderPref: string;
  lifestyle: LifestyleTag[];
  occupation: string;
  bio: string;
  moveInDate: string | null;
  isLooking: boolean;
  createdAt: string;
  updatedAt: string;
}

/** The public view of another user's profile, embedded in a match. */
export interface RoommateProfilePublic extends RoommateProfile {
  user: {
    id: number;
    username: string;
    first_name: string;
    last_name: string;
    avatar: string | null;
    phone: string;
    nid_verified: boolean;
  };
}

export interface RoommateMatch {
  score: number;
  reasons: string[];
  profile: RoommateProfilePublic;
}

export type RoommateRequestStatus = "pending" | "approved" | "rejected";

export interface RoommateRequest {
  id: number;
  sender: RoommateProfilePublic["user"];
  receiver: RoommateProfilePublic["user"];
  message: string;
  status: RoommateRequestStatus;
  statusDisplay: string;
  direction: "incoming" | "outgoing" | "";
  createdAt: string;
  updatedAt: string;
}

export interface RoommateProfilePayload {
  budgetMin: number;
  budgetMax: number;
  preferredArea: string;
  roomTypePref: string;
  genderPref: string;
  lifestyle: LifestyleTag[];
  occupation: string;
  bio: string;
  moveInDate: string | null;
  isLooking: boolean;
}

// ---- Fraud detection ----

export type FraudSeverity = "clean" | "low" | "medium" | "high";
export type FraudReportStatus = "open" | "reviewed" | "dismissed";

export interface FraudStatus {
  roomId: number;
  severity: FraudSeverity;
  score: number;
  flagged: boolean;
  message: string;
}

export interface FraudSignal {
  id: number;
  detector: string;
  detectorDisplay: string;
  severity: FraudSeverity;
  message: string;
  detail: Record<string, unknown>;
  createdAt: string;
}

export interface FraudReport {
  id: number;
  room: Room;
  severity: FraudSeverity;
  severityDisplay: string;
  status: FraudReportStatus;
  statusDisplay: string;
  score: number;
  summary: string;
  signals: FraudSignal[];
  createdAt: string;
  updatedAt: string;
}

// ---- KYC verification (documents + admin review panel) ----

export type KycDocType = "nid" | "passport";
export type KycDocStatus = "pending" | "approved" | "rejected";

export interface KycDocument {
  id: number;
  docType: KycDocType;
  docTypeDisplay: string;
  /** Private file URL — only the owner and admins can fetch it. */
  fileUrl: string;
  status: KycDocStatus;
  statusDisplay: string;
  reviewNote: string;
  createdAt: string;
  reviewedAt: string | null;
}

/** One applicant in the admin KYC review panel. */
export interface KycApplication {
  id: number;
  username: string;
  email: string;
  name: string;
  phone: string;
  role: string;
  nidVerified: boolean;
  documents: KycDocument[];
}

/** Admin review-queue health from GET /users/kyc/sla/. */
export interface KycSla {
  pendingCount: number;
  resolvedCount: number;
  /** Average hours between submission and a decision (all-time). */
  avgReviewHours: number | null;
  last7dDecisions: number;
  last7dAvgReviewHours: number | null;
  prev7dDecisions: number;
  /** This week's decisions minus last week's — negative means the queue grows. */
  decisionDelta7d: number;
  /** Age of the oldest pending document, in hours. */
  pendingOldestHours: number | null;
  /** Which review SLA is currently being missed ("oldest_pending" | "trend_negative"). */
  breaches: string[];
  /** Last 30 days, oldest first: decisions + average review hours per day. */
  trend30d: { date: string; decisions: number; avgReviewHours: number | null }[];
}

/** One KYC decision in the admin history view (append-only audit trail). */
export interface KycAuditEntry {
  id: number;
  action: "kyc.approved" | "kyc.rejected";
  actorUsername: string;
  actorName: string;
  userId: number | null;
  userName: string;
  note: string;
  createdAt: string;
}

// ============================================================
// Phase 10 — Growth & Personalization
// ============================================================

/** A saved room-search the user can be alerted about (Search v2). */
export interface SavedSearch {
  id: number;
  name: string;
  filters: {
    q?: string;
    area?: string;
    room_type?: string;
    gender_preference?: string;
    price_min?: number;
    price_max?: number;
    verified?: boolean;
  };
  lastCheckedAt: string | null;
  createdAt: string;
}

/** Referral program payload (GET /users/referral/). */
export interface ReferralInfo {
  code: string;
  link: string;
  invitedCount: number;
  invited: { username: string; joinedAt: string }[];
}

/** One room's landlord-insights row (GET /rooms/insights/). */
export interface RoomInsightRow {
  id: number;
  title: string;
  price: number;
  area: string;
  roomType: string;
  tier: string;
  verified: boolean;
  views7d: number;
  views30d: number;
  viewsTotal: number;
  wishlistCount: number;
  bookingRequests: number;
  bookingApproved: number;
  areaAvgPrice: number | null;
  priceDeltaPct: number | null;
}

export interface RoomInsights {
  rooms: RoomInsightRow[];
  summary: {
    listingCount: number;
    totalViews30d: number;
    totalWishlists: number;
  };
}

/** Rating breakdown + recent reviews (GET /reviews/summary/?room=). */
export interface ReviewSummary {
  room: number;
  averageRating: number;
  totalReviews: number;
  countsPerStar: Record<"1" | "2" | "3" | "4" | "5", number>;
  recent: ReviewItem[];
}

export interface ReviewItem {
  id: number;
  room: number;
  user: { id: number; username: string; firstName: string; avatar: string | null };
  rating: number;
  comment: string;
  verifiedStay: boolean;
  photos: string[];
  reply: string;
  repliedAt: string | null;
  createdAt: string;
}

/** Similar rooms payload (GET /recommendations/similar/<room_id>/). */
export interface SimilarRoomResult {
  room: Room;
  matchScore: number;
  matchReasons: string[];
}

/** Wishlist share info (GET /wishlist/share-info/). */
export interface WishlistShareInfo {
  token: string;
  link: string;
}
