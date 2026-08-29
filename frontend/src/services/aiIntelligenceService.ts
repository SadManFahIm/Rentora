import { api } from "./api";

// ============================================================
// AI INTELLIGENCE SERVICE — Phase 18 admin dashboard + alerts
// (GET /ai/dashboard/*  POST/PATCH/DELETE /ai/alerts/*)
// All cost figures are ESTIMATED USD from execution telemetry.
// ============================================================

export interface AiTrendPoint {
  date: string;
  count: number;
  errors?: number;
  costUsd?: number;
  avgLatencyMs?: number;
}

export interface AiSummary {
  days: number;
  totalExecutions: number;
  successfulExecutions: number;
  failedExecutions: number;
  timeoutExecutions: number;
  rateLimitedExecutions: number;
  successRate: number;
  errorRate: number;
  avgLatencyMs: number;
  p50LatencyMs: number;
  p95LatencyMs: number;
  p99LatencyMs: number;
  latencySampleSize: number;
  fallbackRate: number;
  estimatedCostUsd: number;
  totalTokens: number;
  inputTokens: number;
  outputTokens: number;
  costSource: string;
  activeFeatures: number;
  activeModels: number;
  openAlerts: number;
  driftStatus: string;
  trend: AiTrendPoint[];
  isEstimatedCost: boolean;
}

export interface AiFeatureRow {
  featureId: string;
  name: string;
  category: string;
  status: string;
  isEnabled: boolean;
  totalExecutions: number;
  successfulExecutions: number;
  failedExecutions: number;
  successRate: number;
  errorRate: number;
  timeoutRate: number;
  fallbackRate: number;
  avgLatencyMs: number;
  p95LatencyMs: number;
  estimatedCostUsd: number;
  activeProvider: string;
  activeModel: string;
  activePrompt: string;
  activePromptVersion: number;
  latestEvaluationScore: number | null;
  latestEvaluationDate: string | null;
  latestEvaluationStatus: string;
  lastExecution: string | null;
  providerFailures: number;
}

export interface AiFeatureDetail {
  featureId: string;
  name: string;
  category: string;
  usage: {
    totalExecutions: number;
    successfulExecutions: number;
    failedExecutions: number;
    successRate: number;
    distinctUsers: number;
    trend: AiTrendPoint[];
  };
  performance: {
    avgLatencyMs: number;
    p50LatencyMs: number;
    p95LatencyMs: number;
    p99LatencyMs: number;
    sampleSize: number;
  };
  reliability: {
    errorRate: number;
    timeoutRate: number;
    fallbackRate: number;
    providerFailures: number;
  };
  cost: {
    estimatedTotalCostUsd: number;
    costPerExecutionUsd: number;
    totalTokens: number;
    byProvider: { provider: string; count: number; costUsd: number }[];
    byModel: {
      provider: string;
      modelName: string;
      modelVersion: string;
      count: number;
      costUsd: number;
    }[];
    isEstimatedCost: boolean;
  };
  quality: {
    latestEvaluationScore: number | null;
    baselineScore: number | null;
    scoreDelta: number | null;
    regressionStatus: string;
    regressionCount: number;
    regressions: unknown[];
    latestEvaluationDate: string | null;
    passRate: number | null;
    datasetKey: string | null;
  };
  configuration: {
    activeProvider: string;
    activeModel: string;
    activePrompt: string;
    activePromptVersion: number;
    featureFlagKey: string;
    fallbackStrategy: string;
    status: string;
    isEnabled: boolean;
  };
  drift: AiDriftRow[];
}

export interface AiModelRow {
  provider: string;
  modelName: string;
  modelVersion: string;
  totalExecutions: number;
  successRate: number;
  errorRate: number;
  timeoutRate: number;
  fallbackRate: number;
  avgLatencyMs: number;
  estimatedCostUsd: number;
  latestEvaluationScore: number | null;
  latestEvaluationPassRate: number | null;
  latestEvaluationDate: string | null;
}

export interface AiModelCompare {
  provider: string;
  modelName: string;
  versionA: AiModelSnapshot | null;
  versionB: AiModelSnapshot | null;
  deltas: {
    scoreDelta: number | null;
    passRateDelta: number | null;
    latencyDeltaMs: number | null;
    costDeltaUsd: number | null;
  };
  winner: "a" | "b" | "tie";
  productionSwitchAutomated: boolean;
}

export interface AiModelSnapshot {
  runId: number;
  runKey: string;
  score: number;
  passRate: number;
  metricScores: Record<string, number>;
  avgLatencyMs: number;
  totalCostUsd: number;
  datasetKey: string | null;
  completedAt: string | null;
}

export interface AiProviderRow {
  provider: string;
  totalRequests: number;
  successRate: number;
  errorRate: number;
  fallbackRate: number;
  avgLatencyMs: number;
  p95LatencyMs: number;
  estimatedCostUsd: number;
  latestHealthWindow: string | null;
  healthWindowSuccessRate: number | null;
  isHealthy: boolean;
  availabilityStatus: string;
}

export interface AiCostDashboard {
  days: number;
  isEstimatedCost: boolean;
  currency: string;
  totalEstimatedCostUsd: number;
  costPerExecutionUsd: number;
  costPerSuccessfulExecutionUsd: number;
  totalTokens: number;
  inputTokens: number;
  outputTokens: number;
  trend: AiTrendPoint[];
  vsPreviousWindowPct: number | null;
  byFeature: { featureKey: string; costUsd: number; count: number }[];
  byProvider: { provider: string; costUsd: number; count: number }[];
  byModel: { provider: string; modelName: string; costUsd: number; count: number }[];
  anomalies: { type: string; message: string; severity: string }[];
}

export interface AiPerformanceDashboard {
  days: number;
  overall: {
    avgLatencyMs: number;
    p50LatencyMs: number;
    p95LatencyMs: number;
    p99LatencyMs: number;
    sampleSize: number;
  };
  dailyTrend: AiTrendPoint[];
  byFeature: AiLatencyBreakdown[];
  byProvider: AiLatencyBreakdown[];
  byModel: AiLatencyBreakdown[];
  abnormalLatencyIncrease: {
    detected: boolean;
    currentAvgMs: number;
    previousAvgMs: number;
    increasePct: number;
    message: string;
  } | null;
}

export interface AiLatencyBreakdown {
  name: string;
  avgLatencyMs: number;
  count: number;
  p95LatencyMs: number;
}

export interface AiErrorDashboard {
  days: number;
  totalErrors: number;
  errorRate: number;
  timeoutCount: number;
  timeoutRate: number;
  fallbackCount: number;
  fallbackRate: number;
  failureTypeBreakdown: { failureType: string; count: number }[];
  statusBreakdown: { status: string; count: number }[];
  byFeature: { featureKey: string; count: number }[];
  byProvider: { provider: string; count: number }[];
  byModel: { modelName: string; count: number }[];
  fallbackReasons: { reason: string; count: number }[];
}

export interface AiQualityDashboard {
  days: number;
  evaluatorTypes: Record<string, string>;
  features: AiQualityRow[];
  metrics: {
    metricKey: string;
    name: string;
    category: string;
    metricType: string;
    isHigherBetter: boolean;
  }[];
}

export interface AiQualityRow {
  featureId: string;
  featureName: string;
  category: string;
  runId: number;
  runKey: string;
  score: number;
  passRate: number;
  metricScores: Record<string, number>;
  datasetKey: string | null;
  provider: string;
  modelName: string;
  promptKey: string | null;
  promptVersion: number | null;
  completedAt: string | null;
}

export interface AiDriftRow {
  modelName: string;
  modelVersion: string;
  metricName: string;
  value: number | null;
  baselineValue: number | null;
  thresholdMin: number | null;
  thresholdMax: number | null;
  thresholdBreached: boolean;
  status: "healthy" | "warning" | "critical" | "unknown";
  windowEnd: string | null;
  lastChecked: string | null;
}

export interface AiPromptRow {
  promptKey: string;
  name: string;
  status: string;
  activeVersion: number | null;
  previousVersion: number | null;
  versionCount: number;
  featureId: string | null;
  defaultModel: string;
  latestEvaluationScore: number | null;
  latestEvaluationPassRate: number | null;
  latestEvaluationMetricScores: Record<string, number>;
  latestEvaluationModel: string | null;
  latestEvaluationDate: string | null;
  lastUpdated: string;
}

export interface AiAlertRule {
  id: number;
  ruleKey: string;
  name: string;
  description: string;
  alertType: string;
  alertTypeDisplay: string;
  metric: string;
  metricDisplay: string;
  operator: string;
  operatorDisplay: string;
  thresholdValue: number;
  featureId: string | null;
  provider: string;
  modelName: string;
  durationMinutes: number;
  consecutiveChecks: number;
  cooldownMinutes: number;
  severity: string;
  severityDisplay: string;
  isEnabled: boolean;
  notifyAdmins: boolean;
  breachCount: number;
  lastMetricValue: number | null;
  lastCheckedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AiAlert {
  id: number;
  alertKey: string;
  rule: number | null;
  ruleKey: string | null;
  alertType: string;
  alertTypeDisplay: string;
  severity: string;
  severityDisplay: string;
  status: string;
  statusDisplay: string;
  title: string;
  message: string;
  metricName: string;
  metricValue: number;
  thresholdValue: number;
  feature: number | null;
  featureId: string | null;
  provider: string;
  modelName: string;
  dedupKey: string;
  breachCount: number;
  acknowledgedBy: number | null;
  acknowledgedByUsername: string | null;
  acknowledgedAt: string | null;
  resolvedBy: number | null;
  resolvedByUsername: string | null;
  resolvedAt: string | null;
  resolutionNote: string;
  meta: Record<string, unknown>;
  triggeredAt: string;
}

export interface NewAiAlertRule {
  ruleKey: string;
  name: string;
  description?: string;
  alertType: string;
  metric: string;
  operator: string;
  thresholdValue: number;
  featureId?: string;
  provider?: string;
  modelName?: string;
  durationMinutes?: number;
  consecutiveChecks?: number;
  cooldownMinutes?: number;
  severity?: string;
  isEnabled?: boolean;
  notifyAdmins?: boolean;
}

// ---- mapping helpers (snake → camel) ----

interface ApiTrendPoint {
  date: string;
  count?: number;
  errors?: number;
  cost_usd?: number;
  avg_latency_ms?: number;
}

const mapTrend = (p: ApiTrendPoint): AiTrendPoint => ({
  date: p.date,
  count: p.count ?? 0,
  errors: p.errors,
  costUsd: p.cost_usd,
  avgLatencyMs: p.avg_latency_ms,
});

function mapApiTrend(raw: ApiTrendPoint[]): AiTrendPoint[] {
  return raw.map(mapTrend);
}

export const aiIntelligenceService = {
  /** GET /ai/dashboard/summary/ */
  async getSummary(days = 30): Promise<AiSummary> {
    const { data } = await api.get<Record<string, unknown>>("/ai/dashboard/summary/", {
      params: { days },
    });
    return {
      days: days,
      totalExecutions: data.total_executions as number,
      successfulExecutions: data.successful_executions as number,
      failedExecutions: data.failed_executions as number,
      timeoutExecutions: data.timeout_executions as number,
      rateLimitedExecutions: data.rate_limited_executions as number,
      successRate: data.success_rate as number,
      errorRate: data.error_rate as number,
      avgLatencyMs: data.avg_latency_ms as number,
      p50LatencyMs: data.p50_latency_ms as number,
      p95LatencyMs: data.p95_latency_ms as number,
      p99LatencyMs: data.p99_latency_ms as number,
      latencySampleSize: data.latency_sample_size as number,
      fallbackRate: data.fallback_rate as number,
      estimatedCostUsd: data.estimated_cost_usd as number,
      totalTokens: data.total_tokens as number,
      inputTokens: data.input_tokens as number,
      outputTokens: data.output_tokens as number,
      costSource: data.cost_source as string,
      activeFeatures: data.active_features as number,
      activeModels: data.active_models as number,
      openAlerts: data.open_alerts as number,
      driftStatus: data.drift_status as string,
      trend: mapApiTrend((data.trend as ApiTrendPoint[]) ?? []),
      isEstimatedCost: data.is_estimated_cost as boolean,
    };
  },

  /** GET /ai/dashboard/features/ */
  async getFeatures(days = 30): Promise<AiFeatureRow[]> {
    const { data } = await api.get<Record<string, unknown>[]>("/ai/dashboard/features/", {
      params: { days },
    });
    return data.map((r) => ({
      featureId: r.feature_id as string,
      name: r.name as string,
      category: r.category as string,
      status: r.status as string,
      isEnabled: r.is_enabled as boolean,
      totalExecutions: r.total_executions as number,
      successfulExecutions: r.successful_executions as number,
      failedExecutions: r.failed_executions as number,
      successRate: r.success_rate as number,
      errorRate: r.error_rate as number,
      timeoutRate: r.timeout_rate as number,
      fallbackRate: r.fallback_rate as number,
      avgLatencyMs: r.avg_latency_ms as number,
      p95LatencyMs: r.p95_latency_ms as number,
      estimatedCostUsd: r.estimated_cost_usd as number,
      activeProvider: r.active_provider as string,
      activeModel: r.active_model as string,
      activePrompt: r.active_prompt as string,
      activePromptVersion: r.active_prompt_version as number,
      latestEvaluationScore:
        r.latest_evaluation_score != null ? (r.latest_evaluation_score as number) : null,
      latestEvaluationDate:
        r.latest_evaluation_date != null ? (r.latest_evaluation_date as string) : null,
      latestEvaluationStatus: r.latest_evaluation_status as string,
      lastExecution: r.last_execution != null ? (r.last_execution as string) : null,
      providerFailures: r.provider_failures as number,
    }));
  },

  /** GET /ai/dashboard/features/:featureId/ */
  async getFeatureDetail(featureId: string, days = 30): Promise<AiFeatureDetail | null> {
    const { data } = await api.get<Record<string, unknown>>(
      `/ai/dashboard/features/${encodeURIComponent(featureId)}/`,
      { params: { days } }
    );
    if (data.error) return null;
    return {
      featureId: data.feature_id as string,
      name: data.name as string,
      category: data.category as string,
      usage: {
        totalExecutions: (data.usage as Record<string, unknown>).total_executions as number,
        successfulExecutions: (data.usage as Record<string, unknown>)
          .successful_executions as number,
        failedExecutions: (data.usage as Record<string, unknown>).failed_executions as number,
        successRate: (data.usage as Record<string, unknown>).success_rate as number,
        distinctUsers: (data.usage as Record<string, unknown>).distinct_users as number,
        trend: mapApiTrend(
          ((data.usage as Record<string, unknown>).trend as ApiTrendPoint[]) ?? []
        ),
      },
      performance: data.performance as AiFeatureDetail["performance"],
      reliability: data.reliability as AiFeatureDetail["reliability"],
      cost: {
        ...(data.cost as Record<string, unknown>),
        byProvider: (
          (data.cost as Record<string, unknown>).by_provider as Record<string, unknown>[]
        ).map((b) => ({
          provider: b.provider as string,
          count: b.count as number,
          costUsd: b.cost_usd as number,
        })),
        byModel: ((data.cost as Record<string, unknown>).by_model as Record<string, unknown>[]).map(
          (b) => ({
            provider: b.provider as string,
            modelName: b.model_name as string,
            modelVersion: b.model_version as string,
            count: b.count as number,
            costUsd: b.cost_usd as number,
          })
        ),
      } as AiFeatureDetail["cost"],
      quality: data.quality as AiFeatureDetail["quality"],
      configuration: data.configuration as AiFeatureDetail["configuration"],
      drift: (data.drift as Record<string, unknown>[]).map(mapDrift),
    };
  },

  /** GET /ai/dashboard/models/ */
  async getModels(days = 30): Promise<AiModelRow[]> {
    const { data } = await api.get<Record<string, unknown>[]>("/ai/dashboard/models/", {
      params: { days },
    });
    return data.map((r) => ({
      provider: r.provider as string,
      modelName: r.model_name as string,
      modelVersion: (r.model_version as string) ?? "",
      totalExecutions: r.total_executions as number,
      successRate: r.success_rate as number,
      errorRate: r.error_rate as number,
      timeoutRate: r.timeout_rate as number,
      fallbackRate: r.fallback_rate as number,
      avgLatencyMs: r.avg_latency_ms as number,
      estimatedCostUsd: r.estimated_cost_usd as number,
      latestEvaluationScore:
        r.latest_evaluation_score != null ? (r.latest_evaluation_score as number) : null,
      latestEvaluationPassRate:
        r.latest_evaluation_pass_rate != null ? (r.latest_evaluation_pass_rate as number) : null,
      latestEvaluationDate:
        r.latest_evaluation_date != null ? (r.latest_evaluation_date as string) : null,
    }));
  },

  /** GET /ai/dashboard/models/compare/ */
  async compareModels(params: {
    provider: string;
    model: string;
    versionA: string;
    versionB: string;
  }): Promise<AiModelCompare> {
    const { data } = await api.get<Record<string, unknown>>("/ai/dashboard/models/compare/", {
      params: {
        provider: params.provider,
        model: params.model,
        version_a: params.versionA,
        version_b: params.versionB,
      },
    });
    return {
      provider: data.provider as string,
      modelName: data.model_name as string,
      versionA: data.version_a ? mapSnapshot(data.version_a as Record<string, unknown>) : null,
      versionB: data.version_b ? mapSnapshot(data.version_b as Record<string, unknown>) : null,
      deltas: data.deltas as AiModelCompare["deltas"],
      winner: data.winner as AiModelCompare["winner"],
      productionSwitchAutomated: data.production_switch_automated as boolean,
    };
  },

  /** GET /ai/dashboard/providers/ */
  async getProviders(days = 30): Promise<AiProviderRow[]> {
    const { data } = await api.get<Record<string, unknown>[]>("/ai/dashboard/providers/", {
      params: { days },
    });
    return data.map((r) => ({
      provider: r.provider as string,
      totalRequests: r.total_requests as number,
      successRate: r.success_rate as number,
      errorRate: r.error_rate as number,
      fallbackRate: r.fallback_rate as number,
      avgLatencyMs: r.avg_latency_ms as number,
      p95LatencyMs: r.p95_latency_ms as number,
      estimatedCostUsd: r.estimated_cost_usd as number,
      latestHealthWindow:
        r.latest_health_window != null ? (r.latest_health_window as string) : null,
      healthWindowSuccessRate:
        r.health_window_success_rate != null ? (r.health_window_success_rate as number) : null,
      isHealthy: r.is_healthy as boolean,
      availabilityStatus: r.availability_status as string,
    }));
  },

  /** GET /ai/dashboard/cost/ */
  async getCost(days = 30): Promise<AiCostDashboard> {
    const { data } = await api.get<Record<string, unknown>>("/ai/dashboard/cost/", {
      params: { days },
    });
    const byFeature = ((data.by_feature as Record<string, unknown>[]) ?? []).map((b) => ({
      featureKey: b.feature_key as string,
      costUsd: b.cost_usd as number,
      count: b.count as number,
    }));
    const byProvider = ((data.by_provider as Record<string, unknown>[]) ?? []).map((b) => ({
      provider: b.provider as string,
      costUsd: b.cost_usd as number,
      count: b.count as number,
    }));
    const byModel = ((data.by_model as Record<string, unknown>[]) ?? []).map((b) => ({
      provider: b.provider as string,
      modelName: b.model_name as string,
      costUsd: b.cost_usd as number,
      count: b.count as number,
    }));
    return {
      days: data.days as number,
      isEstimatedCost: data.is_estimated_cost as boolean,
      currency: data.currency as string,
      totalEstimatedCostUsd: data.total_estimated_cost_usd as number,
      costPerExecutionUsd: data.cost_per_execution_usd as number,
      costPerSuccessfulExecutionUsd: data.cost_per_successful_execution_usd as number,
      totalTokens: data.total_tokens as number,
      inputTokens: data.input_tokens as number,
      outputTokens: data.output_tokens as number,
      trend: mapApiTrend((data.trend as ApiTrendPoint[]) ?? []),
      vsPreviousWindowPct:
        data.vs_previous_window_pct != null ? (data.vs_previous_window_pct as number) : null,
      byFeature,
      byProvider,
      byModel,
      anomalies: ((data.anomalies as Record<string, unknown>[]) ?? []).map((a) => ({
        type: a.type as string,
        message: a.message as string,
        severity: a.severity as string,
      })),
    };
  },

  /** GET /ai/dashboard/performance/ */
  async getPerformance(days = 30): Promise<AiPerformanceDashboard> {
    const { data } = await api.get<Record<string, unknown>>("/ai/dashboard/performance/", {
      params: { days },
    });
    return {
      days: data.days as number,
      overall: data.overall as AiPerformanceDashboard["overall"],
      dailyTrend: mapApiTrend((data.daily_trend as ApiTrendPoint[]) ?? []),
      byFeature: mapBreakdown(data.by_feature as Record<string, unknown>[]),
      byProvider: mapBreakdown(data.by_provider as Record<string, unknown>[]),
      byModel: mapBreakdown(data.by_model as Record<string, unknown>[]),
      abnormalLatencyIncrease:
        data.abnormal_latency_increase as AiPerformanceDashboard["abnormalLatencyIncrease"],
    };
  },

  /** GET /ai/dashboard/errors/ */
  async getErrors(days = 30, featureId?: string): Promise<AiErrorDashboard> {
    const { data } = await api.get<Record<string, unknown>>("/ai/dashboard/errors/", {
      params: { days, feature_id: featureId },
    });
    return {
      days: data.days as number,
      totalErrors: data.total_errors as number,
      errorRate: data.error_rate as number,
      timeoutCount: data.timeout_count as number,
      timeoutRate: data.timeout_rate as number,
      fallbackCount: data.fallback_count as number,
      fallbackRate: data.fallback_rate as number,
      failureTypeBreakdown: ((data.failure_type_breakdown as Record<string, unknown>[]) ?? []).map(
        (b) => ({ failureType: b.failure_type as string, count: b.count as number })
      ),
      statusBreakdown: ((data.status_breakdown as Record<string, unknown>[]) ?? []).map((b) => ({
        status: b.status as string,
        count: b.count as number,
      })),
      byFeature: ((data.by_feature as Record<string, unknown>[]) ?? []).map((b) => ({
        featureKey: b.feature_key as string,
        count: b.count as number,
      })),
      byProvider: ((data.by_provider as Record<string, unknown>[]) ?? []).map((b) => ({
        provider: b.provider as string,
        count: b.count as number,
      })),
      byModel: ((data.by_model as Record<string, unknown>[]) ?? []).map((b) => ({
        modelName: b.model_name as string,
        count: b.count as number,
      })),
      fallbackReasons: ((data.fallback_reasons as Record<string, unknown>[]) ?? []).map((b) => ({
        reason: b.reason as string,
        count: b.count as number,
      })),
    };
  },

  /** GET /ai/dashboard/quality/ */
  async getQuality(days = 180): Promise<AiQualityDashboard> {
    const { data } = await api.get<Record<string, unknown>>("/ai/dashboard/quality/", {
      params: { days },
    });
    return {
      days: data.days as number,
      evaluatorTypes: (data.evaluator_types as Record<string, string>) ?? {},
      features: ((data.features as Record<string, unknown>[]) ?? []).map((r) => ({
        featureId: r.feature_id as string,
        featureName: r.feature_name as string,
        category: r.category as string,
        runId: r.run_id as number,
        runKey: r.run_key as string,
        score: r.score as number,
        passRate: r.pass_rate as number,
        metricScores: (r.metric_scores as Record<string, number>) ?? {},
        datasetKey: r.dataset_key != null ? (r.dataset_key as string) : null,
        provider: r.provider as string,
        modelName: r.model_name as string,
        promptKey: r.prompt_key != null ? (r.prompt_key as string) : null,
        promptVersion: r.prompt_version != null ? (r.prompt_version as number) : null,
        completedAt: r.completed_at != null ? (r.completed_at as string) : null,
      })),
      metrics: ((data.metrics as Record<string, unknown>[]) ?? []).map((m) => ({
        metricKey: m.metric_key as string,
        name: m.name as string,
        category: m.category as string,
        metricType: m.metric_type as string,
        isHigherBetter: m.is_higher_better as boolean,
      })),
    };
  },

  /** GET /ai/dashboard/drift/ */
  async getDrift(modelName?: string): Promise<AiDriftRow[]> {
    const { data } = await api.get<Record<string, unknown>[]>("/ai/dashboard/drift/", {
      params: modelName ? { model_name: modelName } : {},
    });
    return data.map(mapDrift);
  },

  /** GET /ai/dashboard/prompts/ */
  async getPrompts(days = 90): Promise<AiPromptRow[]> {
    const { data } = await api.get<Record<string, unknown>[]>("/ai/dashboard/prompts/", {
      params: { days },
    });
    return data.map((r) => ({
      promptKey: r.prompt_key as string,
      name: r.name as string,
      status: r.status as string,
      activeVersion: r.active_version != null ? (r.active_version as number) : null,
      previousVersion: r.previous_version != null ? (r.previous_version as number) : null,
      versionCount: r.version_count as number,
      featureId: r.feature_id != null ? (r.feature_id as string) : null,
      defaultModel: r.default_model as string,
      latestEvaluationScore:
        r.latest_evaluation_score != null ? (r.latest_evaluation_score as number) : null,
      latestEvaluationPassRate:
        r.latest_evaluation_pass_rate != null ? (r.latest_evaluation_pass_rate as number) : null,
      latestEvaluationMetricScores:
        (r.latest_evaluation_metric_scores as Record<string, number>) ?? {},
      latestEvaluationModel:
        r.latest_evaluation_model != null ? (r.latest_evaluation_model as string) : null,
      latestEvaluationDate:
        r.latest_evaluation_date != null ? (r.latest_evaluation_date as string) : null,
      lastUpdated: r.last_updated as string,
    }));
  },

  // ---- Alerts ----

  /** GET /ai/alerts/rules/ */
  async listAlertRules(filters?: { alertType?: string; metric?: string; enabled?: boolean }) {
    const { data } = await api.get<Record<string, unknown>[]>("/ai/alerts/rules/", {
      params: {
        alert_type: filters?.alertType,
        metric: filters?.metric,
        enabled: filters?.enabled,
      },
    });
    return data.map(mapRule);
  },

  /** POST /ai/alerts/rules/ */
  async createAlertRule(payload: NewAiAlertRule): Promise<AiAlertRule> {
    const { data } = await api.post<Record<string, unknown>>("/ai/alerts/rules/", payload);
    return mapRule(data);
  },

  /** GET /ai/alerts/rules/:id/ */
  async getAlertRule(id: number): Promise<AiAlertRule> {
    const { data } = await api.get<Record<string, unknown>>(`/ai/alerts/rules/${id}/`);
    return mapRule(data);
  },

  /** PATCH /ai/alerts/rules/:id/ */
  async updateAlertRule(id: number, payload: Partial<NewAiAlertRule>): Promise<AiAlertRule> {
    const { data } = await api.patch<Record<string, unknown>>(`/ai/alerts/rules/${id}/`, payload);
    return mapRule(data);
  },

  /** DELETE /ai/alerts/rules/:id/ */
  async deleteAlertRule(id: number): Promise<void> {
    await api.delete(`/ai/alerts/rules/${id}/`);
  },

  /** GET /ai/alerts/ — list with optional filters. */
  async listAlerts(filters?: {
    severity?: string;
    status?: string;
    alertType?: string;
    featureId?: string;
  }) {
    const { data } = await api.get<Record<string, unknown>[]>("/ai/alerts/", {
      params: {
        severity: filters?.severity,
        status: filters?.status,
        alert_type: filters?.alertType,
        feature_id: filters?.featureId,
      },
    });
    return data.map(mapAlert);
  },

  /** GET /ai/alerts/:id/ */
  async getAlert(id: number): Promise<AiAlert> {
    const { data } = await api.get<Record<string, unknown>>(`/ai/alerts/${id}/`);
    return mapAlert(data);
  },

  /** POST /ai/alerts/:id/acknowledge/ */
  async acknowledgeAlert(id: number, note = ""): Promise<AiAlert> {
    const { data } = await api.post<Record<string, unknown>>(`/ai/alerts/${id}/acknowledge/`, {
      note,
    });
    return mapAlert(data);
  },

  /** POST /ai/alerts/:id/resolve/ */
  async resolveAlert(id: number, note = ""): Promise<AiAlert> {
    const { data } = await api.post<Record<string, unknown>>(`/ai/alerts/${id}/resolve/`, {
      note,
    });
    return mapAlert(data);
  },

  /** POST /ai/alerts/:id/suppress/ */
  async suppressAlert(id: number, note = ""): Promise<AiAlert> {
    const { data } = await api.post<Record<string, unknown>>(`/ai/alerts/${id}/suppress/`, {
      note,
    });
    return mapAlert(data);
  },

  /** POST /ai/alerts/evaluate/ — run all enabled rules now. */
  async evaluateAlerts(): Promise<{ evaluated: number; counts: Record<string, number> }> {
    const { data } = await api.post<{ evaluated: number; counts: Record<string, number> }>(
      "/ai/alerts/evaluate/"
    );
    return data;
  },
};

function mapDrift(r: Record<string, unknown>): AiDriftRow {
  return {
    modelName: r.model_name as string,
    modelVersion: r.model_version as string,
    metricName: r.metric_name as string,
    value: r.value != null ? (r.value as number) : null,
    baselineValue: r.baseline_value != null ? (r.baseline_value as number) : null,
    thresholdMin: r.threshold_min != null ? (r.threshold_min as number) : null,
    thresholdMax: r.threshold_max != null ? (r.threshold_max as number) : null,
    thresholdBreached: r.threshold_breached as boolean,
    status: r.status as AiDriftRow["status"],
    windowEnd: r.window_end != null ? (r.window_end as string) : null,
    lastChecked: r.last_checked != null ? (r.last_checked as string) : null,
  };
}

function mapBreakdown(raw: Record<string, unknown>[]): AiLatencyBreakdown[] {
  return (raw ?? []).map((b) => ({
    name: (b.model_name as string) ?? (b.provider as string) ?? (b.feature_key as string) ?? "",
    avgLatencyMs: b.avg_latency_ms as number,
    count: b.count as number,
    p95LatencyMs: b.p95_latency_ms as number,
  }));
}

function mapSnapshot(r: Record<string, unknown>): AiModelSnapshot {
  return {
    runId: r.run_id as number,
    runKey: r.run_key as string,
    score: r.score as number,
    passRate: r.pass_rate as number,
    metricScores: (r.metric_scores as Record<string, number>) ?? {},
    avgLatencyMs: r.avg_latency_ms as number,
    totalCostUsd: r.total_cost_usd as number,
    datasetKey: r.dataset_key != null ? (r.dataset_key as string) : null,
    completedAt: r.completed_at != null ? (r.completed_at as string) : null,
  };
}

function mapRule(r: Record<string, unknown>): AiAlertRule {
  return {
    id: r.id as number,
    ruleKey: r.rule_key as string,
    name: r.name as string,
    description: (r.description as string) ?? "",
    alertType: r.alert_type as string,
    alertTypeDisplay: r.alert_type_display as string,
    metric: r.metric as string,
    metricDisplay: r.metric_display as string,
    operator: r.operator as string,
    operatorDisplay: r.operator_display as string,
    thresholdValue: r.threshold_value as number,
    featureId: r.feature_id != null ? (r.feature_id as string) : null,
    provider: (r.provider as string) ?? "",
    modelName: (r.model_name as string) ?? "",
    durationMinutes: r.duration_minutes as number,
    consecutiveChecks: r.consecutive_checks as number,
    cooldownMinutes: r.cooldown_minutes as number,
    severity: r.severity as string,
    severityDisplay: r.severity_display as string,
    isEnabled: r.is_enabled as boolean,
    notifyAdmins: r.notify_admins as boolean,
    breachCount: r.breach_count as number,
    lastMetricValue: r.last_metric_value != null ? (r.last_metric_value as number) : null,
    lastCheckedAt: r.last_checked_at != null ? (r.last_checked_at as string) : null,
    createdAt: r.created_at as string,
    updatedAt: r.updated_at as string,
  };
}

function mapAlert(r: Record<string, unknown>): AiAlert {
  return {
    id: r.id as number,
    alertKey: r.alert_key as string,
    rule: r.rule != null ? (r.rule as number) : null,
    ruleKey: r.rule_key != null ? (r.rule_key as string) : null,
    alertType: r.alert_type as string,
    alertTypeDisplay: r.alert_type_display as string,
    severity: r.severity as string,
    severityDisplay: r.severity_display as string,
    status: r.status as string,
    statusDisplay: r.status_display as string,
    title: r.title as string,
    message: r.message as string,
    metricName: r.metric_name as string,
    metricValue: r.metric_value as number,
    thresholdValue: r.threshold_value as number,
    feature: r.feature != null ? (r.feature as number) : null,
    featureId: r.feature_id != null ? (r.feature_id as string) : null,
    provider: (r.provider as string) ?? "",
    modelName: (r.model_name as string) ?? "",
    dedupKey: r.dedup_key as string,
    breachCount: r.breach_count as number,
    acknowledgedBy: r.acknowledged_by != null ? (r.acknowledged_by as number) : null,
    acknowledgedByUsername:
      r.acknowledged_by_username != null ? (r.acknowledged_by_username as string) : null,
    acknowledgedAt: r.acknowledged_at != null ? (r.acknowledged_at as string) : null,
    resolvedBy: r.resolved_by != null ? (r.resolved_by as number) : null,
    resolvedByUsername: r.resolved_by_username != null ? (r.resolved_by_username as string) : null,
    resolvedAt: r.resolved_at != null ? (r.resolved_at as string) : null,
    resolutionNote: (r.resolution_note as string) ?? "",
    meta: (r.meta as Record<string, unknown>) ?? {},
    triggeredAt: r.triggered_at as string,
  };
}

export default aiIntelligenceService;
