import { api } from "./api";
import type { AuditEntry } from "../types";

// ============================================================
// AUDIT SERVICE — append-only admin audit trail (admin only)
// ============================================================

interface ApiAuditEntry {
  id: number;
  actor: number | null;
  actor_username: string;
  action: string;
  target_type: string;
  target_id: string;
  detail: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
}

export const auditService = {
  /** GET /audit/ — newest audit entries; `prefix` filters by action prefix
   * (e.g. "moderation", "dispute", "report", "kyc"). */
  async getTrail(prefix?: string): Promise<AuditEntry[]> {
    const { data } = await api.get<ApiAuditEntry[]>("/audit/", {
      params: prefix ? { prefix } : undefined,
    });
    return data.map((e) => ({
      id: e.id,
      actor: e.actor,
      actorUsername: e.actor_username,
      action: e.action,
      targetType: e.target_type,
      targetId: e.target_id,
      detail: e.detail,
      ipAddress: e.ip_address,
      createdAt: e.created_at,
    }));
  },
};

export default auditService;
