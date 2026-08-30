import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import aiIntelligenceService, {
  type AiAlert,
  type AiAlertRule,
  type NewAiAlertRule,
} from "../services/aiIntelligenceService";
import { getApiErrorMessage } from "../services/errors";

// ============================================================
// AI INTELLIGENCE HOOKS — Phase 18 admin dashboard + alerts
// ============================================================

export const aiIntelligenceKeys = {
  all: ["ai-intelligence"] as const,
  summary: (days: number) => [...aiIntelligenceKeys.all, "summary", days] as const,
  features: (days: number) => [...aiIntelligenceKeys.all, "features", days] as const,
  featureDetail: (featureId: string, days: number) =>
    [...aiIntelligenceKeys.all, "feature-detail", featureId, days] as const,
  models: (days: number) => [...aiIntelligenceKeys.all, "models", days] as const,
  modelCompare: (params: unknown) => [...aiIntelligenceKeys.all, "model-compare", params] as const,
  providers: (days: number) => [...aiIntelligenceKeys.all, "providers", days] as const,
  cost: (days: number) => [...aiIntelligenceKeys.all, "cost", days] as const,
  performance: (days: number) => [...aiIntelligenceKeys.all, "performance", days] as const,
  errors: (days: number, featureId?: string) =>
    [...aiIntelligenceKeys.all, "errors", days, featureId ?? "-"] as const,
  quality: (days: number) => [...aiIntelligenceKeys.all, "quality", days] as const,
  drift: (modelName?: string) => [...aiIntelligenceKeys.all, "drift", modelName ?? "-"] as const,
  prompts: (days: number) => [...aiIntelligenceKeys.all, "prompts", days] as const,
  alertRules: (filters?: { alertType?: string; metric?: string; enabled?: boolean }) =>
    [...aiIntelligenceKeys.all, "alert-rules", filters ?? {}] as const,
  alerts: (filters?: { severity?: string; status?: string; alertType?: string }) =>
    [...aiIntelligenceKeys.all, "alerts", filters ?? {}] as const,
  alert: (id: number) => [...aiIntelligenceKeys.all, "alert", id] as const,
};

// ---- Dashboard queries ----

export function useAiSummary(days = 30) {
  return useQuery({
    queryKey: aiIntelligenceKeys.summary(days),
    queryFn: () => aiIntelligenceService.getSummary(days),
  });
}

export function useAiFeatures(days = 30) {
  return useQuery({
    queryKey: aiIntelligenceKeys.features(days),
    queryFn: () => aiIntelligenceService.getFeatures(days),
  });
}

export function useAiFeatureDetail(featureId: string | null, days = 30) {
  return useQuery({
    queryKey: aiIntelligenceKeys.featureDetail(featureId ?? "", days),
    queryFn: () => aiIntelligenceService.getFeatureDetail(featureId!, days),
    enabled: featureId != null && featureId !== "",
  });
}

export function useAiModels(days = 30) {
  return useQuery({
    queryKey: aiIntelligenceKeys.models(days),
    queryFn: () => aiIntelligenceService.getModels(days),
  });
}

export function useAiModelCompare(
  params: { provider: string; model: string; versionA: string; versionB: string } | null
) {
  return useQuery({
    queryKey: aiIntelligenceKeys.modelCompare(params),
    queryFn: () => aiIntelligenceService.compareModels(params!),
    enabled: params != null,
  });
}

export function useAiProviders(days = 30) {
  return useQuery({
    queryKey: aiIntelligenceKeys.providers(days),
    queryFn: () => aiIntelligenceService.getProviders(days),
  });
}

export function useAiCost(days = 30) {
  return useQuery({
    queryKey: aiIntelligenceKeys.cost(days),
    queryFn: () => aiIntelligenceService.getCost(days),
  });
}

export function useAiPerformance(days = 30) {
  return useQuery({
    queryKey: aiIntelligenceKeys.performance(days),
    queryFn: () => aiIntelligenceService.getPerformance(days),
  });
}

export function useAiErrors(days = 30, featureId?: string) {
  return useQuery({
    queryKey: aiIntelligenceKeys.errors(days, featureId),
    queryFn: () => aiIntelligenceService.getErrors(days, featureId),
  });
}

export function useAiQuality(days = 180) {
  return useQuery({
    queryKey: aiIntelligenceKeys.quality(days),
    queryFn: () => aiIntelligenceService.getQuality(days),
  });
}

export function useAiDrift(modelName?: string) {
  return useQuery({
    queryKey: aiIntelligenceKeys.drift(modelName),
    queryFn: () => aiIntelligenceService.getDrift(modelName),
  });
}

export function useAiPrompts(days = 90) {
  return useQuery({
    queryKey: aiIntelligenceKeys.prompts(days),
    queryFn: () => aiIntelligenceService.getPrompts(days),
  });
}

// ---- Alert queries ----

export function useAiAlertRules(filters?: {
  alertType?: string;
  metric?: string;
  enabled?: boolean;
}) {
  return useQuery<AiAlertRule[]>({
    queryKey: aiIntelligenceKeys.alertRules(filters),
    queryFn: () => aiIntelligenceService.listAlertRules(filters),
  });
}

export function useAiAlerts(filters?: { severity?: string; status?: string; alertType?: string }) {
  return useQuery<AiAlert[]>({
    queryKey: aiIntelligenceKeys.alerts(filters),
    queryFn: () => aiIntelligenceService.listAlerts(filters),
  });
}

// ---- Alert mutations ----

export function useCreateAiAlertRule() {
  const queryClient = useQueryClient();
  return useMutation<AiAlertRule, unknown, NewAiAlertRule>({
    mutationFn: (payload) => aiIntelligenceService.createAlertRule(payload),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not create the alert rule."));
    },
    onSuccess: () => {
      toast.success("Alert rule created.");
      queryClient.invalidateQueries({ queryKey: aiIntelligenceKeys.all });
    },
  });
}

export function useUpdateAiAlertRule() {
  const queryClient = useQueryClient();
  return useMutation<AiAlertRule, unknown, { id: number; payload: Partial<NewAiAlertRule> }>({
    mutationFn: ({ id, payload }) => aiIntelligenceService.updateAlertRule(id, payload),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not update the alert rule."));
    },
    onSuccess: (_rule, vars) => {
      toast.success("Alert rule updated.");
      queryClient.invalidateQueries({
        queryKey: aiIntelligenceKeys.alertRules(),
      });
      void vars.id;
    },
  });
}

export function useDeleteAiAlertRule() {
  const queryClient = useQueryClient();
  return useMutation<void, unknown, number>({
    mutationFn: (id) => aiIntelligenceService.deleteAlertRule(id),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not delete the alert rule."));
    },
    onSuccess: () => {
      toast.success("Alert rule deleted.");
      queryClient.invalidateQueries({ queryKey: aiIntelligenceKeys.all });
    },
  });
}

export function useAlertLifecycle() {
  const queryClient = useQueryClient();
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: aiIntelligenceKeys.all });
  };
  const acknowledge = useMutation<AiAlert, unknown, { id: number; note?: string }>({
    mutationFn: ({ id, note = "" }) => aiIntelligenceService.acknowledgeAlert(id, note),
    onError: (error, vars) => {
      toast.error(getApiErrorMessage(error, `Could not acknowledge alert ${vars.id}.`));
    },
    onSuccess: () => {
      toast.success("Alert acknowledged.");
      invalidate();
    },
  });
  const resolve = useMutation<AiAlert, unknown, { id: number; note?: string }>({
    mutationFn: ({ id, note = "" }) => aiIntelligenceService.resolveAlert(id, note),
    onError: (error, vars) => {
      toast.error(getApiErrorMessage(error, `Could not resolve alert ${vars.id}.`));
    },
    onSuccess: () => {
      toast.success("Alert resolved.");
      invalidate();
    },
  });
  const suppress = useMutation<AiAlert, unknown, { id: number; note?: string }>({
    mutationFn: ({ id, note = "" }) => aiIntelligenceService.suppressAlert(id, note),
    onError: (error, vars) => {
      toast.error(getApiErrorMessage(error, `Could not suppress alert ${vars.id}.`));
    },
    onSuccess: () => {
      toast.success("Alert suppressed.");
      invalidate();
    },
  });
  return { acknowledge, resolve, suppress };
}

export function useEvaluateAiAlerts() {
  const queryClient = useQueryClient();
  return useMutation<{ evaluated: number; counts: Record<string, number> }, unknown, void>({
    mutationFn: () => aiIntelligenceService.evaluateAlerts(),
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Could not evaluate alert rules."));
    },
    onSuccess: (result) => {
      const total = result.counts?.triggered ?? 0;
      toast.success(
        total > 0
          ? `Alert evaluation complete — ${total} triggered.`
          : "Alert evaluation complete — no new alerts."
      );
      queryClient.invalidateQueries({ queryKey: aiIntelligenceKeys.all });
    },
  });
}
