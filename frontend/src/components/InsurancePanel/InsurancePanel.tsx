import { useState } from "react";
import { Loader2, ShieldCheck, Sparkles } from "lucide-react";
import {
  useCreditEligibility,
  useCreateInsuranceQuote,
  useInsuranceProducts,
  useInsuranceQuotes,
} from "../../hooks/useInsurance";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Skeleton } from "../ui/skeleton";

/** Insurance & credit panel — request quotes, issue policies, check credit. */
export default function InsurancePanel() {
  const { data: products = [], isLoading: productsLoading } = useInsuranceProducts();
  const { data: quotes = [] } = useInsuranceQuotes();
  const { data: credit } = useCreditEligibility();
  const createQuote = useCreateInsuranceQuote();

  const [periods, setPeriods] = useState<Record<number, number>>({});

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-2">
        <ShieldCheck className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">
            Renter insurance & credit
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Partner-offered policies quoted instantly; check your pre-approved credit limit.
          </p>
        </div>
      </div>

      {credit && (
        <div className="flex flex-col gap-2 rounded-2xl border border-emerald-500/40 bg-emerald-50 p-4 dark:bg-emerald-950/20">
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-700 dark:text-emerald-400">
            <Sparkles className="size-4" /> Credit eligibility ({credit.provider})
          </div>
          <div className="text-xs text-emerald-700/80 dark:text-emerald-400/80">
            Score {credit.creditScore} · pre-approved up to ৳
            {credit.preapprovedLimit.toLocaleString()} {credit.currency}
          </div>
        </div>
      )}

      {productsLoading ? (
        <div className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-32 w-full rounded-2xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {products.map((p) => (
            <div
              key={p.id}
              className="flex flex-col gap-3 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800"
            >
              <div className="flex items-center justify-between">
                <div className="font-display font-bold text-foreground">{p.name}</div>
                <span className="text-xs text-gray-500">by {p.partnerName}</span>
              </div>
              <div className="text-xs text-gray-600 dark:text-gray-400">
                ৳{p.priceMonthly.toLocaleString()}/mo · deductible ৳{p.deductible.toLocaleString()}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(p.coverage).map(([k, v]) => (
                  <span
                    key={k}
                    className="rounded-full bg-gray-100 px-2 py-0.5 text-[0.65rem] font-semibold text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                  >
                    {k}: {String(v)}
                  </span>
                ))}
              </div>
              <div className="mt-auto flex items-center gap-2">
                <Input
                  type="number"
                  min={1}
                  className="h-9 w-24"
                  value={periods[p.id] ?? 12}
                  onChange={(e) => setPeriods({ ...periods, [p.id]: Number(e.target.value) })}
                />
                <span className="text-xs text-gray-500">months</span>
                <Button
                  size="sm"
                  className="ml-auto bg-orange-600 text-white hover:bg-orange-700"
                  disabled={createQuote.isPending}
                  onClick={() =>
                    createQuote.mutate({
                      productId: p.id,
                      coveragePeriod: Math.max(1, periods[p.id] ?? 12),
                    })
                  }
                >
                  {createQuote.isPending ? <Loader2 className="size-4 animate-spin" /> : null} Get
                  quote
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {quotes.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="font-display font-bold text-foreground">My quotes</h3>
          <div className="overflow-x-auto rounded-2xl border border-gray-200 dark:border-gray-800">
            <table className="w-full min-w-[480px] text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-2.5">Product</th>
                  <th className="px-4 py-2.5">Price</th>
                  <th className="px-4 py-2.5">Period</th>
                  <th className="px-4 py-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {quotes.map((q) => (
                  <tr key={q.id}>
                    <td className="px-4 py-2.5 text-foreground">{q.product.name}</td>
                    <td className="px-4 py-2.5 font-semibold text-foreground">
                      ৳{q.price.toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5 text-gray-500">{q.coveragePeriod} months</td>
                    <td className="px-4 py-2.5">
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-semibold capitalize text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                        {q.statusDisplay}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
