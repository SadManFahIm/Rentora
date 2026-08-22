import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { corporateService, type BulkBookingRequest } from "../services/corporateService";
import { getApiErrorMessage } from "../services/errors";
import type { CorporateAccount, CorporateInvoice, CorporateMember } from "../types";

// ============================================================
// CORPORATE QUERY / MUTATION HOOKS
// ============================================================

export const corporateKeys = {
  all: ["corporate"] as const,
  accounts: () => [...corporateKeys.all, "accounts"] as const,
  account: (id: number) => [...corporateKeys.all, "account", id] as const,
  members: (id: number) => [...corporateKeys.all, "members", id] as const,
  invoices: () => [...corporateKeys.all, "invoices"] as const,
  adminOverview: () => [...corporateKeys.all, "admin-overview"] as const,
};

/** Own corporate housing accounts. */
export function useCorporateAccounts() {
  return useQuery<CorporateAccount[]>({
    queryKey: corporateKeys.accounts(),
    queryFn: () => corporateService.listAccounts(),
  });
}

/** Members of one account. */
export function useCorporateMembers(accountId: number | null) {
  return useQuery<CorporateMember[]>({
    queryKey: corporateKeys.members(accountId ?? -1),
    queryFn: () => corporateService.listMembers(accountId as number),
    enabled: accountId != null,
  });
}

/** Own corporate invoices. */
export function useCorporateInvoices() {
  return useQuery<CorporateInvoice[]>({
    queryKey: corporateKeys.invoices(),
    queryFn: () => corporateService.listInvoices(),
  });
}

/** Company-admin overview (approvals dashboard). */
export function useCorporateAdminOverview(enabled = true) {
  return useQuery({
    queryKey: corporateKeys.adminOverview(),
    queryFn: () => corporateService.adminOverview(),
    enabled,
  });
}

export function useCreateCorporateAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof corporateService.createAccount>[0]) =>
      corporateService.createAccount(input),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not create the corporate account."));
    },
    onSuccess: () => {
      toast.success("Corporate account created.");
      queryClient.invalidateQueries({ queryKey: corporateKeys.accounts() });
    },
  });
}

export function useAddCorporateMembers() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { accountId: number; emails: string[] }) =>
      corporateService.addMembers(vars.accountId, vars.emails),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not invite the members."));
    },
    onSuccess: (_members, vars) => {
      toast.success("Members invited.");
      queryClient.invalidateQueries({ queryKey: corporateKeys.members(vars.accountId) });
    },
  });
}

/** Bulk-book a room for several corporate members at once. */
export function useBulkBooking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: BulkBookingRequest) => corporateService.bulkBooking(request),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not place the bulk booking."));
    },
    onSuccess: (result) => {
      toast.success(`Bulk booking placed: ${result.succeeded} succeeded, ${result.failed} failed.`);
      queryClient.invalidateQueries({ queryKey: corporateKeys.all });
    },
  });
}

/** Finalize a draft invoice. */
export function useGenerateInvoice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => corporateService.generateInvoice(id),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not generate the invoice."));
    },
    onSuccess: () => {
      toast.success("Invoice generated.");
      queryClient.invalidateQueries({ queryKey: corporateKeys.invoices() });
    },
  });
}

/** Company-admin account decision (approve/suspend/reactivate). */
export function useCorporateAdminAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; action: "approve" | "suspend" | "reactivate" }) =>
      corporateService.adminAction(vars.id, vars.action),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not update the account."));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: corporateKeys.all });
    },
  });
}
