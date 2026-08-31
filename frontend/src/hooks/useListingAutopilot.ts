import { useCallback, useEffect, useRef, useState } from "react";
import {
  approveAutopilotProposal,
  bulkApproveAutopilotProposals,
  getAutopilotOverview,
  listAutopilotAnalyses,
  listAutopilotProposals,
  rejectAutopilotProposal,
  type AutopilotAnalysis,
  type AutopilotOverview,
  type AutopilotProposal,
  type AutopilotProposalStatus,
} from "../services/listingAutopilotService";

export interface ListingAutopilotState {
  overview: AutopilotOverview | null;
  proposals: AutopilotProposal[];
  analyses: AutopilotAnalysis[];
  loading: boolean;
  busyKey: string | null;
  error: string;
  lastAction: string;
}

const EMPTY_STATE: ListingAutopilotState = {
  overview: null,
  proposals: [],
  analyses: [],
  loading: true,
  busyKey: null,
  error: "",
  lastAction: "",
};

interface UseListingAutopilotReturn extends ListingAutopilotState {
  reload: () => Promise<void>;
  setStatusFilter: (status: AutopilotProposalStatus | "") => void;
  approve: (proposalKey: string) => Promise<void>;
  reject: (proposalKey: string, reason?: string) => Promise<void>;
  approveAll: () => Promise<void>;
}

function extractErrorMessage(err: unknown): string {
  if (typeof err === "object" && err !== null) {
    const anyErr = err as {
      response?: { data?: { error?: unknown; message?: unknown } };
      message?: unknown;
    };
    const raw = anyErr.response?.data?.error ?? anyErr.response?.data?.message ?? anyErr.message;
    if (typeof raw === "string" && raw.trim()) return raw.trim();
  }
  return "Couldn't reach the autopilot right now — try again.";
}

/**
 * Phase 19.3 AI Listing Autopilot client state for landlords.
 *
 * The autopilot is *not* chat-driven: a weekly Celery run mints typed,
 * grounded proposals (title/description/amenities/photos/price/renewal) that
 * the landlord reviews here. Approve applies exactly once (server-side replay
 * guard); reject frees the slot for a future week. "Approve all" batches every
 * currently-valid pending proposal.
 */
export default function useListingAutopilot(): UseListingAutopilotReturn {
  const [state, setState] = useState<ListingAutopilotState>(EMPTY_STATE);
  const [statusFilter, setStatusFilter] = useState<AutopilotProposalStatus | "">("");
  const mountedRef = useRef(true);

  const reload = useCallback(async () => {
    try {
      const [overview, proposals, analyses] = await Promise.all([
        getAutopilotOverview(),
        listAutopilotProposals(statusFilter),
        listAutopilotAnalyses(),
      ]);
      if (!mountedRef.current) return;
      setState((prev) => ({
        ...prev,
        overview,
        proposals: proposals.proposals,
        analyses: analyses.analyses,
        loading: false,
        error: "",
      }));
    } catch (err) {
      if (!mountedRef.current) return;
      setState((prev) => ({
        ...prev,
        loading: false,
        error: extractErrorMessage(err),
      }));
    }
  }, [statusFilter]);

  useEffect(() => {
    mountedRef.current = true;
    void reload();
    return () => {
      mountedRef.current = false;
    };
  }, [reload]);

  // ---- consent actions ----
  const approve = useCallback(
    async (proposalKey: string) => {
      setState((prev) => ({ ...prev, busyKey: proposalKey, error: "" }));
      try {
        await approveAutopilotProposal(proposalKey);
        await reload();
        setState((prev) => ({
          ...prev,
          lastAction: `Applied ${proposalKey.slice(0, 8)}…`,
        }));
      } catch (err) {
        const message = extractErrorMessage(err);
        setState((prev) => ({ ...prev, error: message }));
        throw err;
      } finally {
        setState((prev) => ({ ...prev, busyKey: null }));
      }
    },
    [reload]
  );

  const reject = useCallback(
    async (proposalKey: string, reason?: string) => {
      setState((prev) => ({ ...prev, busyKey: proposalKey, error: "" }));
      try {
        await rejectAutopilotProposal(proposalKey, reason);
        await reload();
        setState((prev) => ({ ...prev, lastAction: `Rejected ${proposalKey.slice(0, 8)}…` }));
      } catch (err) {
        const message = extractErrorMessage(err);
        setState((prev) => ({ ...prev, error: message }));
        throw err;
      } finally {
        setState((prev) => ({ ...prev, busyKey: null }));
      }
    },
    [reload]
  );

  const approveAll = useCallback(async () => {
    setState((prev) => ({ ...prev, busyKey: "all", error: "" }));
    try {
      const pending = state.proposals.filter((p) => p.status === "pending");
      if (pending.length === 0) return;
      const result = await bulkApproveAutopilotProposals(pending.map((p) => p.key));
      await reload();
      setState((prev) => ({
        ...prev,
        lastAction: `Bulk applied ${result.applied.length} proposal(s), skipped ${result.skipped.length}.`,
      }));
    } catch (err) {
      const message = extractErrorMessage(err);
      setState((prev) => ({ ...prev, error: message }));
      throw err;
    } finally {
      setState((prev) => ({ ...prev, busyKey: null }));
    }
  }, [reload, state.proposals]);

  return { ...state, reload, setStatusFilter, approve, reject, approveAll };
}
