import { api } from "./api";
import type {
  RoommateMatch,
  RoommateProfile,
  RoommateProfilePayload,
  RoommateRequest,
} from "../types";

// ============================================================
// ROOMMATE SERVICE — /roommates/ endpoints
// ============================================================

interface ApiUser {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  avatar: string | null;
  phone: string;
  nid_verified: boolean;
}

interface ApiRoommateProfile {
  id: number;
  username: string;
  budget_min: string | number;
  budget_max: string | number;
  preferred_area: string;
  room_type_pref: string;
  gender_pref: string;
  lifestyle: string[];
  occupation: string;
  bio: string;
  move_in_date: string | null;
  is_looking: boolean;
  created_at: string;
  updated_at: string;
  user?: ApiUser;
}

interface ApiMatch {
  score: number;
  reasons: string[];
  profile: ApiRoommateProfile;
}

interface ApiRequest {
  id: number;
  sender: ApiUser;
  receiver: ApiUser;
  message: string;
  status: string;
  status_display: string;
  direction: string;
  created_at: string;
  updated_at: string;
}

function mapProfile(api: ApiRoommateProfile): RoommateProfile {
  return {
    id: api.id,
    username: api.username,
    budgetMin: Number(api.budget_min),
    budgetMax: Number(api.budget_max),
    preferredArea: api.preferred_area,
    roomTypePref: api.room_type_pref,
    genderPref: api.gender_pref,
    lifestyle: api.lifestyle as RoommateProfile["lifestyle"],
    occupation: api.occupation,
    bio: api.bio,
    moveInDate: api.move_in_date,
    isLooking: api.is_looking,
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}

function mapMatch(api: ApiMatch): RoommateMatch {
  const profile = { ...mapProfile(api.profile), user: api.profile.user! };
  return { score: api.score, reasons: api.reasons, profile };
}

function mapRequest(api: ApiRequest): RoommateRequest {
  return {
    id: api.id,
    sender: api.sender,
    receiver: api.receiver,
    message: api.message,
    status: api.status as RoommateRequest["status"],
    statusDisplay: api.status_display,
    direction: api.direction as RoommateRequest["direction"],
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}

export const roommateService = {
  /** GET /roommates/profile/ — null when the caller has no profile yet. */
  async getMyProfile(): Promise<RoommateProfile | null> {
    try {
      const { data } = await api.get<ApiRoommateProfile>("/roommates/profile/");
      return mapProfile(data);
    } catch (error) {
      // 404 = no profile yet, which is a legitimate state, not an error.
      if ((error as { response?: { status?: number } }).response?.status === 404) {
        return null;
      }
      throw error;
    }
  },

  /** PUT /roommates/profile/ — upsert (create on first call, update after). */
  async saveMyProfile(payload: RoommateProfilePayload): Promise<RoommateProfile> {
    const body = {
      budget_min: payload.budgetMin,
      budget_max: payload.budgetMax,
      preferred_area: payload.preferredArea,
      room_type_pref: payload.roomTypePref,
      gender_pref: payload.genderPref,
      lifestyle: payload.lifestyle,
      occupation: payload.occupation,
      bio: payload.bio,
      move_in_date: payload.moveInDate,
      is_looking: payload.isLooking,
    };
    const { data } = await api.put<ApiRoommateProfile>("/roommates/profile/", body);
    return mapProfile(data);
  },

  /** GET /roommates/matches/ — best-first scored candidates. */
  async getMatches(): Promise<RoommateMatch[]> {
    const { data } = await api.get<ApiMatch[]>("/roommates/matches/");
    return data.map(mapMatch);
  },

  /** GET /roommates/requests/ — my requests (incoming + outgoing). */
  async getMyRequests(): Promise<RoommateRequest[]> {
    const { data } = await api.get<ApiRequest[]>("/roommates/requests/");
    return data.map(mapRequest);
  },

  /** POST /roommates/requests/ — send a request to another user. */
  async sendRequest(receiverId: number, message: string): Promise<RoommateRequest> {
    const { data } = await api.post<ApiRequest>("/roommates/requests/", {
      receiver_id: receiverId,
      message,
    });
    return mapRequest(data);
  },

  /** POST /roommates/requests/{id}/action/ — approve or reject. */
  async respondToRequest(requestId: number, action: "approve" | "reject"): Promise<RoommateRequest> {
    const { data } = await api.post<ApiRequest>(
      `/roommates/requests/${requestId}/action/`,
      { action }
    );
    return mapRequest(data);
  },
};

export default roommateService;
