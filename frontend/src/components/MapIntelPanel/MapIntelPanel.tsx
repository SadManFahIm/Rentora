import { useMemo, useState } from "react";
import {
  Bot,
  Building2,
  Check,
  Crosshair,
  Landmark as LandmarkIcon,
  Loader2,
  MapPin,
  Search,
  Sparkles,
  Star,
  TrainFront,
  TrendingUp,
  Wallet,
  X,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import {
  mapIntelService,
  mapIntelKeys,
  type AreaIntel,
  type IdealArea,
} from "../../services/mapIntelService";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { useValueScores } from "../../hooks/useMapIntel";
import { haversineKm, walkingMinutes, formatDistance } from "../../lib/mapUtils";
import type { Room } from "../../types";

export type MapIntelMode = "ai" | "areas" | "affordability" | "ideal" | "commute" | null;

interface MapIntelPanelProps {
  open: boolean;
  mode: MapIntelMode;
  onMode: (mode: MapIntelMode) => void;
  onClose: () => void;
  rooms: Room[];
  onFlyTo: (lat: number, lng: number, zoom?: number) => void;
  onSetRadius: (lat: number, lng: number, label: string, km?: number) => void;
  selectedArea: string | null;
  onSelectArea: (area: string | null) => void;
  dark: boolean;
  /** Destination for commute / ideal-area ranking — owned by the map page so
   * clicking the map to drop a pin and the panel stay in sync. */
  destination: { lat: number; lng: number; label: string } | null;
  onSetDestination: (d: { lat: number; lng: number; label: string } | null) => void;
  pickDestination: boolean;
  onTogglePick: () => void;
}

const BUDGETS = [5000, 8000, 10000, 12000, 15000, 20000, 25000];

const AI_EXAMPLES = [
  "উত্তরায় ১২ হাজারের মধ্যে furnished room",
  "metro er kache room, Banani under 15k",
  "Mirpur-এ AC single room ১০ হাজারের নিচে",
];

export default function MapIntelPanel({
  open,
  mode,
  onMode,
  onClose,
  rooms,
  onFlyTo,
  onSetRadius,
  selectedArea,
  onSelectArea,
  destination,
  pickDestination,
  onTogglePick,
}: MapIntelPanelProps) {
  const [aiQuery, setAiQuery] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiResult, setAiResult] = useState<{
    count: number;
    intent: Record<string, unknown>;
    rooms: Room[];
    target: { lat: number; lng: number; name: string } | null;
  } | null>(null);
  const [budget, setBudget] = useState(12000);
  const [maxCommute, setMaxCommute] = useState(30);
  const [compareAreas, setCompareAreas] = useState<string[]>([]);

  const { data: allStats } = useQuery({
    queryKey: mapIntelKeys.stats(),
    queryFn: () => mapIntelService.getStats(),
    staleTime: 10 * 60_000,
  });

  const { data: afford } = useQuery({
    queryKey: mapIntelKeys.affordability(budget),
    queryFn: () => mapIntelService.getAffordability(budget),
    enabled: mode === "affordability",
    staleTime: 60_000,
  });

  const { data: ideal } = useQuery({
    queryKey: mapIntelKeys.ideal({
      budget,
      work_lat: destination?.lat,
      work_lng: destination?.lng,
      max_commute: maxCommute,
    }),
    queryFn: () =>
      mapIntelService.getIdealAreas({
        budget,
        work_lat: destination?.lat,
        work_lng: destination?.lng,
        max_commute: maxCommute,
      }),
    enabled: mode === "ideal",
    staleTime: 60_000,
  });

  // Value scores for the current viewport (markers/popups).
  const roomIds = useMemo(() => rooms.map((r) => r.id), [rooms]);
  const { data: valueScores } = useValueScores(roomIds.slice(0, 40));

  // Commute estimates from each visible room to the chosen destination.
  const commuteRows = useMemo(() => {
    if (mode !== "commute" || !destination) return null;
    const { lat, lng } = destination;
    return rooms
      .map((room) => {
        const km = haversineKm(room.lat, room.lng, lat, lng);
        return { room, km, walkMin: walkingMinutes(km) };
      })
      .sort((a, b) => a.walkMin - b.walkMin)
      .slice(0, 30);
  }, [mode, rooms, destination]);

  const visibleWithinCommute = useMemo(() => {
    if (!commuteRows) return null;
    return commuteRows.filter((c) => c.walkMin <= maxCommute);
  }, [commuteRows, maxCommute]);

  if (!open) return null;

  const runAiSearch = async (query: string) => {
    if (!query.trim()) return;
    setAiBusy(true);
    setAiResult(null);
    try {
      const res = await mapIntelService.mapSearch(query);
      setAiResult({
        count: res.count,
        intent: res.intent,
        rooms: res.rooms,
        target: res.target,
      });
      if (res.target) {
        // Fly to the matched area/metro and search near it.
        onFlyTo(res.target.lat, res.target.lng, 13);
        onSetRadius(res.target.lat, res.target.lng, res.target.name, 2);
      }
    } finally {
      setAiBusy(false);
    }
  };

  const statsFor = (area: string): AreaIntel | undefined => allStats?.find((s) => s.area === area);

  return (
    <div className="pointer-events-auto absolute bottom-4 right-4 z-30 flex max-h-[calc(100dvh-9rem)] w-[min(24rem,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white/95 shadow-2xl backdrop-blur dark:border-gray-700 dark:bg-gray-900/95">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-gray-100 px-4 py-3 dark:border-gray-800">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-violet-600 to-blue-600 text-white">
          <Sparkles className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="font-display text-sm font-bold text-foreground">Map Intelligence</div>
          <div className="text-[11px] text-gray-500 dark:text-gray-400">
            Ask the map — real data, live listings
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close map intelligence"
          className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
        >
          <X className="size-4" />
        </button>
      </div>

      {/* Mode tabs */}
      <div className="flex flex-wrap gap-1.5 border-b border-gray-100 px-3 py-2 dark:border-gray-800">
        {(
          [
            ["ai", "AI Search", Bot],
            ["areas", "Areas", LandmarkIcon],
            ["affordability", "Budget", Wallet],
            ["ideal", "Ideal Area", Star],
            ["commute", "Commute", TrainFront],
          ] as const
        ).map(([m, label, Icon]) => (
          <button
            key={m}
            type="button"
            onClick={() => onMode(mode === m ? null : m)}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors",
              mode === m
                ? "bg-violet-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
            )}
          >
            <Icon className="size-3.5" />
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {/* ---- AI SEARCH ---- */}
        {mode === "ai" && (
          <div className="space-y-3">
            <div>
              <label
                htmlFor="map-ai-query"
                className="mb-1 block text-xs font-semibold text-gray-600 dark:text-gray-400"
              >
                Ask in Bangla, English or Banglish
              </label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-gray-400" />
                <input
                  id="map-ai-query"
                  value={aiQuery}
                  onChange={(e) => setAiQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void runAiSearch(aiQuery);
                  }}
                  placeholder='"Uttara 10k er moddhe furnished room"'
                  className="h-10 w-full rounded-xl border border-gray-200 bg-white pl-9 pr-3 text-sm placeholder:text-gray-400 focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-200 dark:border-gray-700 dark:bg-gray-900 dark:placeholder:text-gray-500 dark:focus:border-violet-500 dark:focus:ring-violet-900"
                />
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {AI_EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    type="button"
                    onClick={() => {
                      setAiQuery(ex);
                      void runAiSearch(ex);
                    }}
                    className="rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-[11px] font-medium text-violet-700 hover:bg-violet-100 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-300 dark:hover:bg-violet-950"
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </div>

            {aiBusy && (
              <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                <Loader2 className="size-3.5 animate-spin" /> Searching listings…
              </div>
            )}

            {aiResult && (
              <div className="space-y-2 rounded-xl border border-violet-200 bg-violet-50/60 p-3 dark:border-violet-800/60 dark:bg-violet-950/30">
                <div className="flex items-center gap-2 text-sm font-bold text-foreground">
                  <Sparkles className="size-4 text-violet-600" />
                  {aiResult.count} matching rooms
                </div>
                <div className="flex flex-wrap gap-1">
                  {(aiResult.intent.areas as string[])?.map((a) => (
                    <span
                      key={a}
                      className="rounded-full border border-violet-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-violet-700 dark:border-violet-800 dark:bg-gray-900 dark:text-violet-300"
                    >
                      {a}
                    </span>
                  ))}
                  {aiResult.intent.budget_max != null && (
                    <span className="rounded-full border border-violet-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-violet-700 dark:border-violet-800 dark:bg-gray-900 dark:text-violet-300">
                      ≤ ৳{Number(aiResult.intent.budget_max).toLocaleString()}
                    </span>
                  )}
                  {(aiResult.intent.amenities as string[])?.map((a) => (
                    <span
                      key={a}
                      className="rounded-full border border-violet-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-violet-700 dark:border-violet-800 dark:bg-gray-900 dark:text-violet-300"
                    >
                      {a}
                    </span>
                  ))}
                  {!!aiResult.intent.metro_walk && (
                    <span className="rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-[10px] font-semibold text-teal-700 dark:border-teal-800 dark:bg-teal-950/40 dark:text-teal-300">
                      🚇 near metro
                    </span>
                  )}
                </div>
                {aiResult.rooms.length > 0 && (
                  <ul className="space-y-1">
                    {aiResult.rooms.slice(0, 5).map((room) => (
                      <li key={room.id}>
                        <button
                          type="button"
                          onClick={() => onFlyTo(room.lat, room.lng, 15)}
                          className="flex w-full items-center gap-2 rounded-lg bg-white px-2 py-1.5 text-left text-xs transition-colors hover:bg-violet-100 dark:bg-gray-900 dark:hover:bg-violet-950/40"
                        >
                          <MapPin className="size-3 shrink-0 text-violet-600" />
                          <span className="min-w-0 flex-1 truncate font-semibold text-foreground">
                            {room.name}
                          </span>
                          <span className="shrink-0 font-bold text-orange-600">
                            ৳{room.price.toLocaleString()}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {aiResult.target && (
                  <p className="text-[11px] text-gray-500 dark:text-gray-400">
                    Map flew to <b>{aiResult.target.name}</b> — results update as you pan.
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* ---- AREA INTELLIGENCE ---- */}
        {mode === "areas" && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Tap an area to inspect it — rent stats, demand, metro access and trend from live data.
              Select up to 3 to compare.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {(allStats ?? [])
                .filter((s) => s.listings > 0)
                .map((s) => (
                  <button
                    key={s.area}
                    type="button"
                    onClick={() => {
                      onSelectArea(selectedArea === s.area ? null : s.area);
                      onFlyTo(s.lat ?? 23.78, s.lng ?? 90.4, 12);
                    }}
                    className={cn(
                      "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                      selectedArea === s.area
                        ? "border-violet-500 bg-violet-600 text-white"
                        : "border-gray-200 bg-white text-gray-700 hover:border-violet-300 hover:bg-violet-50 hover:text-violet-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:border-violet-600 dark:hover:bg-violet-950/40 dark:hover:text-violet-300"
                    )}
                  >
                    {s.area} · {s.listings}
                  </button>
                ))}
            </div>

            {selectedArea && (
              <AreaIntelCard
                stats={statsFor(selectedArea)}
                onFly={onFlyTo}
                onAddCompare={(area) =>
                  setCompareAreas((prev) =>
                    prev.includes(area)
                      ? prev.filter((a) => a !== area)
                      : [...prev, area].slice(0, 3)
                  )
                }
                inCompare={compareAreas.includes(selectedArea)}
              />
            )}

            {compareAreas.length >= 2 && (
              <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800">
                      <th className="px-2 py-2 font-semibold text-gray-500 dark:text-gray-400">
                        Metric
                      </th>
                      {compareAreas.map((a) => (
                        <th key={a} className="px-2 py-2 font-bold text-foreground">
                          {a}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[
                      [
                        "Avg rent",
                        (s: AreaIntel) => (s.avg_rent ? `৳${s.avg_rent.toLocaleString()}` : "—"),
                      ],
                      [
                        "Median rent",
                        (s: AreaIntel) =>
                          s.median_rent ? `৳${s.median_rent.toLocaleString()}` : "—",
                      ],
                      ["Listings", (s: AreaIntel) => String(s.listings)],
                      ["Demand", (s: AreaIntel) => s.demand.label],
                      [
                        "Metro access",
                        (s: AreaIntel) => (s.metro_access != null ? `${s.metro_access}/100` : "—"),
                      ],
                      [
                        "Price trend",
                        (s: AreaIntel) =>
                          s.price_trend_pct != null
                            ? `${s.price_trend_pct > 0 ? "+" : ""}${s.price_trend_pct}%`
                            : "—",
                      ],
                    ].map(([label, fn]) => (
                      <tr
                        key={String(label)}
                        className="border-b border-gray-100 dark:border-gray-800"
                      >
                        <td className="px-2 py-1.5 font-semibold text-gray-500 dark:text-gray-400">
                          {String(label)}
                        </td>
                        {compareAreas.map((a) => {
                          const s = statsFor(a);
                          return (
                            <td key={a} className="px-2 py-1.5 font-medium text-foreground">
                              {s ? (fn as (s: AreaIntel) => string)(s) : "—"}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ---- AFFORDABILITY ---- */}
        {mode === "affordability" && (
          <div className="space-y-3">
            <div>
              <label
                htmlFor="aff-budget"
                className="mb-1 block text-xs font-semibold text-gray-600 dark:text-gray-400"
              >
                My budget
              </label>
              <div className="flex items-center gap-2">
                <input
                  id="aff-budget"
                  type="range"
                  min={5000}
                  max={25000}
                  step={1000}
                  value={budget}
                  onChange={(e) => setBudget(Number(e.target.value))}
                  className="h-2 flex-1 cursor-pointer accent-violet-600"
                />
                <span className="w-24 shrink-0 rounded-lg bg-violet-50 px-2 py-1 text-center text-xs font-bold text-violet-700 dark:bg-violet-950/40 dark:text-violet-300">
                  ৳{budget.toLocaleString()}
                </span>
              </div>
            </div>
            <p className="text-[11px] text-gray-500 dark:text-gray-400">
              % of currently listed rooms in each area that fit your budget — real listing shares,
              not an estimate.
            </p>
            <div className="space-y-1.5">
              {(afford ?? []).map((a) => (
                <button
                  key={a.area}
                  type="button"
                  onClick={() => {
                    onSelectArea(a.area);
                    onFlyTo(a.lat ?? 23.78, a.lng ?? 90.4, 12);
                  }}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/60"
                >
                  <span className="w-24 shrink-0 font-semibold text-foreground">{a.area}</span>
                  <span className="h-2 flex-1 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
                    <span
                      className="block h-full rounded-full"
                      style={{
                        width: `${a.percent}%`,
                        backgroundColor:
                          a.percent >= 70 ? "#10b981" : a.percent >= 40 ? "#f59e0b" : "#ef4444",
                      }}
                    />
                  </span>
                  <span className="w-10 shrink-0 text-right font-bold text-foreground">
                    {a.percent}%
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ---- IDEAL AREA ---- */}
        {mode === "ideal" && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Tell us your budget and (optionally) your destination — Rentora ranks the best areas
              for you, with the reasons why.
            </p>
            <div className="flex items-center gap-2">
              <label className="text-xs font-semibold text-gray-600 dark:text-gray-400">
                Budget
              </label>
              <select
                value={budget}
                onChange={(e) => setBudget(Number(e.target.value))}
                className="h-9 flex-1 rounded-lg border border-gray-200 bg-white px-2 text-sm dark:border-gray-700 dark:bg-gray-900"
              >
                {BUDGETS.map((b) => (
                  <option key={b} value={b}>
                    ৳{b.toLocaleString()}/mo
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs font-semibold text-gray-600 dark:text-gray-400">
                Max commute
              </label>
              <select
                value={maxCommute}
                onChange={(e) => setMaxCommute(Number(e.target.value))}
                className="h-9 flex-1 rounded-lg border border-gray-200 bg-white px-2 text-sm dark:border-gray-700 dark:bg-gray-900"
              >
                {[15, 20, 30, 45, 60].map((m) => (
                  <option key={m} value={m}>
                    {m} min
                  </option>
                ))}
              </select>
            </div>
            <div>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-xs font-semibold text-gray-600 dark:text-gray-400">
                  Destination (office / university)
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  className={cn(
                    "h-7 rounded-lg text-[11px]",
                    pickDestination && "border-violet-500 text-violet-600 dark:text-violet-300"
                  )}
                  onClick={onTogglePick}
                >
                  {pickDestination ? (
                    <>
                      <Check className="size-3" /> Click the map
                    </>
                  ) : (
                    <>
                      <Crosshair className="size-3" /> {destination?.label ?? "Set on map"}
                    </>
                  )}
                </Button>
              </div>
              {destination && (
                <p className="text-[11px] text-gray-500 dark:text-gray-400">
                  Destination: {destination.label} · {destination.lat.toFixed(4)},
                  {destination.lng.toFixed(4)}
                </p>
              )}
            </div>
            {ideal && ideal.length > 0 && (
              <div className="space-y-2">
                {ideal.map((area, i) => (
                  <IdealAreaCard
                    key={area.area}
                    rank={i + 1}
                    area={area}
                    onFly={() => {
                      const s = statsFor(area.area);
                      if (s) onFlyTo(area.lat ?? 23.78, area.lng ?? 90.4, 12);
                      void s;
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* ---- COMMUTE ---- */}
        {mode === "commute" && (
          <div className="space-y-3">
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Walking-time estimate from each visible listing to your destination. Tap{" "}
              <b>Set on map</b> to pick a point.
            </p>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className={cn(
                  "h-8 flex-1 rounded-lg text-xs",
                  pickDestination && "border-teal-500 text-teal-600 dark:text-teal-300"
                )}
                onClick={onTogglePick}
              >
                {pickDestination ? "Click the map to drop it" : "🎯 Set destination on map"}
              </Button>
              <select
                value={maxCommute}
                onChange={(e) => setMaxCommute(Number(e.target.value))}
                aria-label="Maximum commute minutes"
                className="h-8 rounded-lg border border-gray-200 bg-white px-2 text-xs dark:border-gray-700 dark:bg-gray-900"
              >
                {[15, 20, 30, 45, 60].map((m) => (
                  <option key={m} value={m}>
                    ≤ {m} min
                  </option>
                ))}
              </select>
            </div>
            {destination && (
              <p className="text-[11px] text-gray-500 dark:text-gray-400">
                Destination: {destination.label} ·{" "}
                {visibleWithinCommute ? (
                  <b className="text-teal-600 dark:text-teal-400">
                    {" "}
                    {visibleWithinCommute.length} rooms within {maxCommute} min
                  </b>
                ) : (
                  " no destination set"
                )}
              </p>
            )}
            {commuteRows && (
              <ul className="space-y-1">
                {commuteRows.map(({ room, km, walkMin }) => (
                  <li key={room.id}>
                    <button
                      type="button"
                      onClick={() => onFlyTo(room.lat, room.lng, 15)}
                      className={cn(
                        "flex w-full items-center gap-2 rounded-lg border px-2 py-1.5 text-left text-xs transition-colors",
                        walkMin <= maxCommute
                          ? "border-teal-200 bg-teal-50/60 hover:bg-teal-100 dark:border-teal-800 dark:bg-teal-950/30 dark:hover:bg-teal-950/60"
                          : "border-gray-100 bg-white opacity-60 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-900 dark:hover:bg-gray-800"
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate font-semibold text-foreground">
                        {room.name}
                      </span>
                      <span className="shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
                        {formatDistance(km)}
                      </span>
                      <span
                        className={cn(
                          "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold",
                          walkMin <= maxCommute
                            ? "bg-teal-600 text-white"
                            : "bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                        )}
                      >
                        🚶 {walkMin} min
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* ---- Value scores in the sidebar ---- */}
        {valueScores && roomIds.length > 0 && (
          <div className="border-t border-gray-100 pt-2 dark:border-gray-800">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-bold text-foreground">
              <Star className="size-3.5 text-amber-500" /> Value scores (visible rooms)
            </div>
            <div className="flex flex-wrap gap-1.5">
              {rooms.slice(0, 10).map((room) => {
                const vs = valueScores[room.id];
                if (!vs) return null;
                return (
                  <button
                    key={room.id}
                    type="button"
                    onClick={() => onFlyTo(room.lat, room.lng, 15)}
                    className="flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-800 transition-colors hover:bg-amber-100 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300 dark:hover:bg-amber-950/70"
                    title={`${room.name} — ${vs.score}/100 value`}
                  >
                    ⭐ {vs.score}
                    <span className="max-w-16 truncate text-gray-500 dark:text-gray-400">
                      {room.name}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function AreaIntelCard({
  stats,
  onFly,
  onAddCompare,
  inCompare,
}: {
  stats?: AreaIntel;
  onFly: (lat: number, lng: number, zoom?: number) => void;
  onAddCompare: (area: string) => void;
  inCompare: boolean;
}) {
  if (!stats) {
    return (
      <div className="rounded-xl border border-gray-200 p-3 text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
        No data yet for this area.
      </div>
    );
  }
  const row = (label: string, value: string) => (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
      <span className="text-xs font-bold text-foreground">{value}</span>
    </div>
  );
  return (
    <div className="rounded-xl border border-violet-200 bg-violet-50/50 p-3 dark:border-violet-800/60 dark:bg-violet-950/30">
      <div className="mb-1 flex items-center justify-between">
        <div className="flex items-center gap-1.5 font-display text-sm font-bold text-foreground">
          <Building2 className="size-4 text-violet-600" /> {stats.area}
        </div>
        <button
          type="button"
          onClick={() => onAddCompare(stats.area)}
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-bold transition-colors",
            inCompare
              ? "bg-violet-600 text-white"
              : "bg-white text-violet-700 hover:bg-violet-100 dark:bg-gray-900 dark:text-violet-300"
          )}
        >
          {inCompare ? "✓ Compare" : "+ Compare"}
        </button>
      </div>
      <div className="grid grid-cols-2 gap-x-3">
        <div>
          {row("Avg rent", stats.avg_rent ? `৳${stats.avg_rent.toLocaleString()}` : "—")}
          {row("Median rent", stats.median_rent ? `৳${stats.median_rent.toLocaleString()}` : "—")}
          {row("Listings", String(stats.listings))}
          {row("Available", String(stats.available))}
        </div>
        <div>
          {row("Avg size", stats.avg_size_sqft ? `${stats.avg_size_sqft} sqft` : "—")}
          {row("Demand", stats.demand.label)}
          {row("Metro access", stats.metro_access != null ? `${stats.metro_access}/100` : "—")}
          {row(
            "Price trend",
            stats.price_trend_pct != null
              ? `${stats.price_trend_pct > 0 ? "+" : ""}${stats.price_trend_pct}%`
              : "—"
          )}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold text-gray-600 dark:bg-gray-900 dark:text-gray-300">
          👀 {stats.demand.views_30d} views / 30d
        </span>
        <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold text-gray-600 dark:bg-gray-900 dark:text-gray-300">
          💾 {stats.demand.saves_30d} saves
        </span>
        <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold text-gray-600 dark:bg-gray-900 dark:text-gray-300">
          📅 {stats.demand.bookings_30d} bookings
        </span>
      </div>
      <Button
        size="sm"
        variant="outline"
        className="mt-2 h-7 w-full rounded-lg text-[11px]"
        onClick={() => onFly(stats.lat ?? 23.78, stats.lng ?? 90.4, 12)}
      >
        <TrendingUp className="size-3" /> Explore {stats.area}
      </Button>
    </div>
  );
}

function IdealAreaCard({
  rank,
  area,
  onFly,
}: {
  rank: number;
  area: IdealArea;
  onFly: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onFly}
      className="w-full rounded-xl border border-gray-200 p-3 text-left transition-colors hover:border-violet-300 hover:bg-violet-50/50 dark:border-gray-700 dark:hover:border-violet-600 dark:hover:bg-violet-950/30"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex size-6 items-center justify-center rounded-full bg-violet-600 text-xs font-bold text-white">
            {rank}
          </span>
          <span className="font-display text-sm font-bold text-foreground">{area.area}</span>
        </div>
        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
          ⭐ {area.score}/100
        </span>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {area.avg_rent && (
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gray-600 dark:bg-gray-800 dark:text-gray-300">
            Avg ৳{area.avg_rent.toLocaleString()}
          </span>
        )}
        {area.commute_minutes != null && (
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gray-600 dark:bg-gray-800 dark:text-gray-300">
            🚇 {area.commute_minutes} min commute
          </span>
        )}
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-semibold text-gray-600 dark:bg-gray-800 dark:text-gray-300">
          {area.affordability_pct}% fits budget
        </span>
      </div>
      <ul className="mt-1.5 space-y-0.5">
        {area.reasons.slice(0, 3).map((r) => (
          <li
            key={r}
            className="flex items-start gap-1 text-[11px] text-gray-500 dark:text-gray-400"
          >
            <Check className="mt-0.5 size-3 shrink-0 text-emerald-600" />
            {r}
          </li>
        ))}
      </ul>
    </button>
  );
}
