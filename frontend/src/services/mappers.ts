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
  ChatUser,
  ChatMessage,
  ChatMessageType,
  ChatMessageStatus,
  ChatRoom,
  ChatRoomType,
  ChatSafetyInfo,
  Dispute,
  DisputeEvidence,
  ModerationOverview,
  PhotoModerationItem,
  Report,
  ReportCategory,
  ReportStatus,
  ReviewModerationItem,
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
  /** Optional in the schema — the backend model has a default. */
  is_primary?: boolean;
  created_at: string;
  /** Phase 16 — optimized WebP variants keyed by size (thumbnail|small|medium|large). */
  variants?: Record<string, string>;
}

export interface ApiOwner {
  id: number;
  username: string;
  /** Optional in the schema (User model allows blank names). */
  first_name?: string;
  last_name?: string;
  avatar?: string | null;
  phone?: string;
  nid_verified?: boolean;
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
  /** Optional in the schema — the backend model has a default. */
  gender_preference?: string;
  size_sqft: number;
  /** Optional in the schema — the backend model has a default. */
  is_available?: boolean;
  tier?: string;
  tier_expires_at?: string | null;
  is_featured: boolean;
  /** Optional in the schema (aggregate computed per room). */
  rating?: string | number;
  total_reviews?: number;
  verified?: boolean;
  owner?: ApiOwner | null;
  images?: ApiRoomImage[];
  created_at: string;
  distance_km?: number | null;
  proximity?: {
    nearest_university: { key: string; name: string; distance_km: number } | null;
    nearest_metro: { key: string; name: string; distance_km: number } | null;
  } | null;
  /** Optional in the schema — only present when a confident prediction
   * exists and the gap clears PRICE_ANOMALY_THRESHOLD. */
  price_anomaly?: {
    available: boolean;
    predicted_price: number;
    difference_percentage: number;
    direction: "above_market" | "below_market";
    badge: string;
  } | null;
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
  security_deposit_amount: string | number;
  security_deposit_paid: boolean;
  security_deposit_refunded: boolean;
  created_at: string;
  /** Tier 3 behavioral trust signals of the booking's tenant. */
  tenant_trust_signals?: {
    tenant_verified: boolean;
    nid_verified: boolean;
    completed_bookings: number;
    profile_complete: boolean;
  };
}

export interface ApiNotification {
  id: number;
  notification_type: string;
  notification_type_display: string;
  title: string;
  message: string;
  /** Optional in the schema — the backend model has a default. */
  is_read?: boolean;
  action_url: string;
  created_at: string;
}

export interface ApiChatUser {
  id: number;
  username: string;
  /** Optional in the schema (User model allows blank names). */
  first_name?: string;
  last_name?: string;
  avatar?: string | null;
  nid_verified?: boolean;
  tenant_verified?: boolean;
  /** Tier 3 behavioral trust signals (completed bookings etc.). */
  trust_signals?: {
    tenant_verified: boolean;
    nid_verified: boolean;
    completed_bookings: number;
    profile_complete: boolean;
  };
}

export interface ApiChatMessage {
  id: number;
  chat_room: number;
  sender: ApiChatUser;
  content: string;
  message_type: string;
  file_url: string;
  is_read: boolean;
  status: string;
  /** Sender edited the message (null when never edited). */
  edited_at?: string | null;
  /** Soft-delete flag — content is a generic notice when true. */
  is_deleted?: boolean;
  created_at: string;
  /** Chat safety engine (Phase 12.3) — attached to warned/flagged/blocked. */
  safety?: {
    risk_level: string;
    outcome: string;
    blocked: boolean;
    warning?: string;
    detectors?: { key: string; label: string }[];
  };
}

export interface ApiReport {
  id: number;
  reporter_username: string;
  reporter_name: string;
  target_user: number;
  target_username: string;
  target_name: string;
  message: number | null;
  category: string;
  category_display: string;
  description: string;
  status: string;
  status_display: string;
  action_taken: string;
  action_taken_display: string;
  admin_note: string;
  created_at: string;
  resolved_at: string | null;
}

export interface ApiReviewModeration {
  id: number;
  review: number;
  room_id: number;
  room_title: string;
  author_username: string;
  author_name: string;
  rating: number;
  comment_preview: string;
  status: string;
  status_display: string;
  risk_score: number;
  signals: { key: string; label: string }[];
  admin_note: string;
  reviewed_by_username: string;
  created_at: string;
  reviewed_at: string | null;
}

export interface ApiPhotoModeration {
  id: number;
  target_type: string;
  target_type_display: string;
  room: number | null;
  room_title: string;
  review: number | null;
  image_url: string;
  phash: string;
  status: string;
  status_display: string;
  risk_score: number;
  signals: { key: string; label: string }[];
  admin_note: string;
  uploaded_by_username: string;
  reviewed_by_username: string;
  created_at: string;
  reviewed_at: string | null;
}

export interface ApiDisputeEvidence {
  id: number;
  dispute: number;
  uploaded_by: number;
  uploaded_by_username: string;
  kind: string;
  kind_display: string;
  content: string;
  file: string | null;
  created_at: string;
}

export interface ApiDispute {
  id: number;
  booking: number;
  room_id: number;
  room_title: string;
  opened_by: number;
  opened_by_username: string;
  other_party_username: string;
  category: string;
  category_display: string;
  description: string;
  status: string;
  status_display: string;
  decision: string;
  decision_display: string;
  decision_amount: string | number | null;
  resolution: string;
  evidence: ApiDisputeEvidence[];
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export interface ApiChatRoom {
  id: number;
  room_type: string;
  listing: number | null;
  listing_title: string | null;
  participants: ApiChatUser[];
  other_participant: ApiChatUser | null;
  is_other_user_online: boolean | null;
  last_message: ApiChatMessage | null;
  unread_count: number;
  created_at: string;
  updated_at: string;
}

export interface ApiUser {
  pk?: number;
  id?: number;
  username: string;
  email: string;
  /** Optional in the schema (User model allows blank names). */
  first_name?: string;
  last_name?: string;
  phone?: string;
  avatar?: string | null;
  role?: string;
  is_staff?: boolean;
  gender?: string;
  nid_verified?: boolean;
  tenant_verified?: boolean;
  bio?: string;
  date_of_birth?: string | null;
  otp_enabled?: boolean;
  passkeys?: {
    id: string;
    name: string;
    created_at: string;
    last_used_at: string | null;
  }[];
}

// ---- helpers ----

const capitalize = (s: string): string => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

const roomTypeLabel = (value: string): RoomType => capitalize(value) as RoomType;

const genderLabel = (value: string): GenderPref => capitalize(value) as GenderPref;

const FALLBACK_IMAGE = (id: number): string =>
  `https://picsum.photos/seed/rentora-room-${id}/600/400`;

function pickImage(room: ApiRoom): string {
  const images = room.images ?? [];
  if (images.length === 0) return FALLBACK_IMAGE(room.id);
  const primary = images.find((img) => img.is_primary) ?? images[0];
  return primary.image;
}

/** Phase 16 — the primary image's optimized WebP variants (when generated). */
function pickVariants(room: ApiRoom): Room["imgVariants"] {
  const images = room.images ?? [];
  if (images.length === 0) return undefined;
  const primary = images.find((img) => img.is_primary) ?? images[0];
  const variants = primary.variants;
  if (!variants || typeof variants !== "object") return undefined;
  return {
    thumbnail: variants.thumbnail,
    small: variants.small,
    medium: variants.medium,
    large: variants.large,
  };
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
    rating: Number(api.rating ?? 0),
    reviews: api.total_reviews ?? 0,
    img: pickImage(api),
    imgVariants: pickVariants(api),
    amenities: api.amenities ?? [],
    // gender_preference is optional in the schema (model default) — default
    // to the backend's own default so the card never renders an empty badge.
    gender: genderLabel(api.gender_preference ?? "any"),
    // is_available is optional in the schema (model default True).
    available: api.is_available ?? true,
    tier: (api.tier as Room["tier"]) ?? "free",
    tierExpiresAt: api.tier_expires_at ?? null,
    featured: api.is_featured || api.tier === "featured" || api.tier === "premium",
    description: api.description ?? "",
    size: api.size_sqft,
    owner,
    ownerId: api.owner?.id ?? null,
    ownerAvatar: initials(owner),
    verified: api.verified ?? false,
    distanceKm: api.distance_km != null ? Number(api.distance_km) : null,
    proximity: api.proximity
      ? {
          nearestUniversity: api.proximity.nearest_university
            ? {
                key: api.proximity.nearest_university.key,
                name: api.proximity.nearest_university.name,
                distanceKm: Number(api.proximity.nearest_university.distance_km),
              }
            : null,
          nearestMetro: api.proximity.nearest_metro
            ? {
                key: api.proximity.nearest_metro.key,
                name: api.proximity.nearest_metro.name,
                distanceKm: Number(api.proximity.nearest_metro.distance_km),
              }
            : null,
        }
      : null,
    priceAnomaly: api.price_anomaly
      ? {
          predictedPrice: Number(api.price_anomaly.predicted_price),
          differencePercentage: api.price_anomaly.difference_percentage,
          direction: api.price_anomaly.direction,
          badge: api.price_anomaly.badge,
        }
      : null,
  };
}

export function mapBooking(api: ApiBooking): Booking {
  // The mapped Booking extends the room's mapped fields; attach the tenant
  // trust signals so landlord booking rows can show completed stays.
  return {
    ...mapRoom(api.room),
    bookingId: api.id,
    status: api.status,
    date: formatDate(api.check_in),
    checkIn: api.check_in,
    monthlyRent: Number(api.monthly_rent),
    securityDepositAmount: Number(api.security_deposit_amount ?? 0),
    securityDepositPaid: api.security_deposit_paid ?? false,
    securityDepositRefunded: api.security_deposit_refunded ?? false,
    tenantTrustSignals: api.tenant_trust_signals
      ? {
          tenantVerified: api.tenant_trust_signals.tenant_verified,
          completedBookings: api.tenant_trust_signals.completed_bookings,
        }
      : undefined,
  };
}

export function mapNotification(api: ApiNotification): Notification {
  return {
    id: api.id,
    text: api.message || api.title,
    read: api.is_read ?? false,
    time: relativeTime(api.created_at),
  };
}

export function mapChatUser(api: ApiChatUser): ChatUser {
  return {
    id: api.id,
    username: api.username,
    firstName: api.first_name ?? "",
    lastName: api.last_name ?? "",
    avatar: api.avatar ?? null,
    nidVerified: api.nid_verified,
    tenantVerified: api.tenant_verified,
    completedBookings: api.trust_signals?.completed_bookings ?? 0,
  };
}

export function mapChatMessage(api: ApiChatMessage): ChatMessage {
  return {
    id: api.id,
    chatRoomId: api.chat_room,
    sender: mapChatUser(api.sender),
    content: api.content,
    messageType: api.message_type as ChatMessageType,
    fileUrl: api.file_url,
    status: api.status as ChatMessageStatus,
    createdAt: api.created_at,
    editedAt: api.edited_at ?? null,
    isDeleted: api.is_deleted ?? false,
    safety: api.safety
      ? {
          riskLevel: api.safety.risk_level as ChatSafetyInfo["riskLevel"],
          outcome: api.safety.outcome as ChatSafetyInfo["outcome"],
          blocked: api.safety.blocked,
          warning: api.safety.warning,
          detectors: api.safety.detectors,
        }
      : undefined,
  };
}

export function mapReport(api: ApiReport): Report {
  return {
    id: api.id,
    reporterUsername: api.reporter_username,
    reporterName: api.reporter_name,
    targetUserId: api.target_user,
    targetUsername: api.target_username,
    targetName: api.target_name,
    messageId: api.message,
    category: api.category as ReportCategory,
    categoryDisplay: api.category_display,
    description: api.description,
    status: api.status as ReportStatus,
    statusDisplay: api.status_display,
    actionTaken: api.action_taken,
    actionTakenDisplay: api.action_taken_display,
    adminNote: api.admin_note,
    createdAt: api.created_at,
    resolvedAt: api.resolved_at,
  };
}

export function mapReviewModeration(api: ApiReviewModeration): ReviewModerationItem {
  return {
    id: api.id,
    review: api.review,
    roomId: api.room_id,
    roomTitle: api.room_title,
    authorUsername: api.author_username,
    authorName: api.author_name,
    rating: api.rating,
    commentPreview: api.comment_preview,
    status: api.status as ReviewModerationItem["status"],
    statusDisplay: api.status_display,
    riskScore: api.risk_score,
    signals: api.signals,
    adminNote: api.admin_note,
    reviewedByUsername: api.reviewed_by_username,
    createdAt: api.created_at,
    reviewedAt: api.reviewed_at,
  };
}

export function mapPhotoModeration(api: ApiPhotoModeration): PhotoModerationItem {
  return {
    id: api.id,
    targetType: api.target_type as PhotoModerationItem["targetType"],
    targetTypeDisplay: api.target_type_display,
    room: api.room,
    roomTitle: api.room_title,
    review: api.review,
    imageUrl: api.image_url,
    phash: api.phash,
    status: api.status as PhotoModerationItem["status"],
    statusDisplay: api.status_display,
    riskScore: api.risk_score,
    signals: api.signals,
    adminNote: api.admin_note,
    uploadedByUsername: api.uploaded_by_username,
    reviewedByUsername: api.reviewed_by_username,
    createdAt: api.created_at,
    reviewedAt: api.reviewed_at,
  };
}

export function mapModerationOverview(api: Record<string, number>): ModerationOverview {
  return {
    reviews: api.reviews ?? 0,
    reviewsPending: api.reviews_pending ?? 0,
    reviewsFlagged: api.reviews_flagged ?? 0,
    reviewsApproved: api.reviews_approved ?? 0,
    reviewsRejected: api.reviews_rejected ?? 0,
    photos: api.photos ?? 0,
    photosPending: api.photos_pending ?? 0,
    photosFlagged: api.photos_flagged ?? 0,
    photosApproved: api.photos_approved ?? 0,
    photosRejected: api.photos_rejected ?? 0,
  };
}

export function mapDisputeEvidence(api: ApiDisputeEvidence): DisputeEvidence {
  return {
    id: api.id,
    dispute: api.dispute,
    uploadedBy: api.uploaded_by,
    uploadedByUsername: api.uploaded_by_username,
    kind: api.kind as DisputeEvidence["kind"],
    kindDisplay: api.kind_display,
    content: api.content,
    file: api.file,
    createdAt: api.created_at,
  };
}

export function mapDispute(api: ApiDispute): Dispute {
  return {
    id: api.id,
    booking: api.booking,
    roomId: api.room_id,
    roomTitle: api.room_title,
    openedBy: api.opened_by,
    openedByUsername: api.opened_by_username,
    otherPartyUsername: api.other_party_username,
    category: api.category as Dispute["category"],
    categoryDisplay: api.category_display,
    description: api.description,
    status: api.status as Dispute["status"],
    statusDisplay: api.status_display,
    decision: api.decision as Dispute["decision"],
    decisionDisplay: api.decision_display,
    decisionAmount: api.decision_amount != null ? Number(api.decision_amount) : null,
    resolution: api.resolution,
    evidence: (api.evidence ?? []).map(mapDisputeEvidence),
    createdAt: api.created_at,
    updatedAt: api.updated_at,
    resolvedAt: api.resolved_at,
  };
}

export function mapChatRoom(api: ApiChatRoom): ChatRoom {
  return {
    id: api.id,
    roomType: api.room_type as ChatRoomType,
    listingId: api.listing,
    listingTitle: api.listing_title,
    participants: api.participants.map(mapChatUser),
    otherParticipant: api.other_participant ? mapChatUser(api.other_participant) : null,
    isOtherUserOnline: api.is_other_user_online,
    lastMessage: api.last_message ? mapChatMessage(api.last_message) : null,
    unreadCount: api.unread_count,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
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
    isStaff: api.is_staff,
    avatar: api.avatar ?? null,
    phone: api.phone,
    bio: api.bio,
    nidVerified: api.nid_verified,
    tenantVerified: api.tenant_verified,
    otpEnabled: api.otp_enabled ?? false,
    passkeys: api.passkeys,
  };
}
