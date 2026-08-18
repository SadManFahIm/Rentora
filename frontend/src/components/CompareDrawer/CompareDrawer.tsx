import { useMemo, useState } from "react";
import { Check, Loader2, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import tier4Service from "../../services/tier4Service";
import { cn } from "../../lib/utils";

interface CompareDrawerProps {
  roomIds: number[];
  onRemove: (id: number) => void;
  onClear: () => void;
}

/** Side-by-side comparison table for 2–5 selected listings (Tier 4). */
export default function CompareDrawer({ roomIds, onRemove, onClear }: CompareDrawerProps) {
  const [open, setOpen] = useState(false);
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["room-compare", roomIds],
    queryFn: () => tier4Service.compare(roomIds),
    enabled: open && roomIds.length >= 2,
    staleTime: 60_000,
  });

  const columns = useMemo(() => {
    if (!data) return [];
    return [
      { key: "price", render: (r: (typeof data.rooms)[0]) => `৳${r.price.toLocaleString()}` },
      {
        key: "price_per_sqft",
        render: (r: (typeof data.rooms)[0]) =>
          r.price_per_sqft != null ? `৳${r.price_per_sqft.toFixed(2)}` : "—",
      },
      { key: "area", render: (r: (typeof data.rooms)[0]) => r.area },
      { key: "room_type", render: (r: (typeof data.rooms)[0]) => r.room_type },
      {
        key: "verified",
        render: (r: (typeof data.rooms)[0]) =>
          r.verified ? (
            <span className="text-emerald-600 dark:text-emerald-400">✓ Verified</span>
          ) : (
            "—"
          ),
      },
      {
        key: "size_sqft",
        render: (r: (typeof data.rooms)[0]) => (r.size_sqft ? `${r.size_sqft} sqft` : "—"),
      },
      {
        key: "amenities",
        render: (r: (typeof data.rooms)[0]) => (r.amenities.length ? r.amenities.join(", ") : "—"),
      },
      {
        key: "market_position",
        render: (r: (typeof data.rooms)[0]) => r.market_position ?? "—",
      },
      {
        key: "quality",
        render: (r: (typeof data.rooms)[0]) =>
          r.quality_score != null ? `${r.quality_score} / 100` : "—",
      },
    ];
  }, [data]);

  return (
    <>
      {/* Floating compare bar — always visible once ≥1 room selected */}
      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-gray-200 bg-white/95 p-3 shadow-lg backdrop-blur dark:border-gray-700 dark:bg-gray-900/95">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">
            Compare ({roomIds.length}/5)
          </span>
          {roomIds.map((id) => (
            <span
              key={id}
              className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300"
            >
              #{id}
              <button
                type="button"
                aria-label={`Remove listing ${id} from comparison`}
                onClick={() => onRemove(id)}
                className="rounded-full p-0.5 hover:bg-gray-200 dark:hover:bg-gray-700"
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              onClick={onClear}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              disabled={roomIds.length < 2}
              className={cn(
                "rounded-lg px-3 py-1.5 text-xs font-semibold text-white transition",
                roomIds.length >= 2
                  ? "bg-indigo-600 hover:bg-indigo-700"
                  : "cursor-not-allowed bg-gray-400"
              )}
            >
              {open ? "Hide comparison" : `Compare (${roomIds.length})`}
            </button>
          </div>
        </div>
      </div>

      {/* Comparison drawer */}
      {open && (
        <div className="fixed inset-x-0 bottom-16 z-30 mx-auto max-w-5xl overflow-x-auto rounded-t-xl border border-gray-200 bg-white p-4 shadow-2xl dark:border-gray-700 dark:bg-gray-900">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-bold text-foreground">
              🤖 AI Property Comparison
              {data?.summary.cheapest && (
                <span className="ml-2 text-xs font-normal text-gray-500">
                  Cheapest: <b>{data.summary.cheapest.title}</b> (৳
                  {data.summary.cheapest.price.toLocaleString()})
                </span>
              )}
            </h3>
            <button
              type="button"
              aria-label="Close comparison"
              onClick={() => setOpen(false)}
              className="rounded-lg p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800"
            >
              <X className="size-4" />
            </button>
          </div>

          {isLoading && (
            <div className="flex items-center gap-2 py-8 text-sm text-gray-500">
              <Loader2 className="size-4 animate-spin" /> Comparing listings…
            </div>
          )}
          {isError && (
            <div className="py-8 text-center text-sm text-rose-600">
              Couldn&apos;t load the comparison.
              <button type="button" onClick={() => refetch()} className="ml-2 underline">
                Retry
              </button>
            </div>
          )}
          {data && (
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="p-2 text-left text-xs font-semibold text-gray-500">Feature</th>
                  {data.rooms.map((r) => (
                    <th key={r.id} className="p-2 text-left align-top">
                      <div className="flex items-start gap-1">
                        <span className="line-clamp-2 font-semibold text-foreground">
                          {r.title}
                        </span>
                        <button
                          type="button"
                          aria-label={`Remove ${r.title}`}
                          onClick={() => onRemove(r.id)}
                          className="rounded p-0.5 text-gray-400 hover:text-rose-500"
                        >
                          <X className="size-3.5" />
                        </button>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {columns.map((col) => (
                  <tr key={col.key} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="p-2 text-xs font-semibold text-gray-500">
                      {data.columns[col.key]?.label ?? col.key}
                    </td>
                    {data.rooms.map((r) => (
                      <td key={r.id} className="p-2 text-foreground">
                        {col.render(r)}
                      </td>
                    ))}
                  </tr>
                ))}
                {data.summary.best_value && (
                  <tr>
                    <td className="p-2 text-xs font-semibold text-gray-500">Best value</td>
                    <td
                      colSpan={data.rooms.length}
                      className="p-2 text-emerald-600 dark:text-emerald-400"
                    >
                      <Check className="mr-1 inline size-3.5" />
                      {data.summary.best_value.title} — ৳
                      {data.summary.best_value.price_per_sqft.toFixed(2)}/sqft
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
      )}
    </>
  );
}
