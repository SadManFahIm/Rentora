import { Link } from "react-router-dom";
import { ShieldCheck, ShoppingBag, Sparkles } from "lucide-react";
import { useApp } from "../../context/AppContext";
import { useInsuranceProducts } from "../../hooks/useInsurance";
import { useAddonServices } from "../../hooks/useMarketplace";
import { Button } from "../../components/ui/button";
import { Skeleton } from "../../components/ui/skeleton";
import { useState } from "react";

const CATEGORIES = ["cleaning", "relocation", "repairs", "furniture", "utilities", "insurance"];

/** Public services hub — add-on marketplace (auth) + renter insurance (public). */
export default function Services() {
  const { user } = useApp();
  const [category, setCategory] = useState<string | undefined>(undefined);
  const { data: insurance = [], isLoading: insuranceLoading } = useInsuranceProducts();
  const { data: addons = [], isLoading: addonsLoading } = useAddonServices(category);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-10 px-4 py-8">
      <div className="flex flex-col gap-2">
        <h1 className="font-display text-3xl font-bold text-foreground">
          Services &amp; protections
        </h1>
        <p className="max-w-2xl text-gray-600 dark:text-gray-400">
          Add-on services for your stay — cleaning, relocation, repairs, furniture and utilities —
          plus partner-offered renter insurance with instant quotes.
        </p>
      </div>

      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 font-display text-xl font-bold text-foreground">
          <ShoppingBag className="size-5 text-orange-600" /> Add-on services
        </h2>
        {!user ? (
          <div className="flex flex-col items-start gap-3 rounded-2xl border border-dashed border-gray-300 p-6 dark:border-gray-700">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Log in to browse the marketplace, place orders and get AI recommendations for your
              bookings.
            </p>
            <Button asChild className="bg-orange-600 text-white hover:bg-orange-700">
              <Link to="/auth">Log in / Register</Link>
            </Button>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => setCategory(undefined)}
                className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition-colors ${
                  !category
                    ? "bg-orange-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
                }`}
              >
                All
              </button>
              {CATEGORIES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCategory(c)}
                  className={`rounded-full px-3.5 py-1.5 text-xs font-semibold capitalize transition-colors ${
                    category === c
                      ? "bg-orange-600 text-white"
                      : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
            {addonsLoading ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-36 rounded-2xl" />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {addons.map((s) => (
                  <div
                    key={s.id}
                    className="flex flex-col gap-2 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800"
                  >
                    <div className="flex items-center justify-between">
                      <span className="rounded-full bg-orange-500/10 px-2 py-0.5 text-[0.65rem] font-bold capitalize text-orange-600">
                        {s.categoryDisplay}
                      </span>
                      <span className="text-xs text-gray-500">★ {s.ratingAvg.toFixed(1)}</span>
                    </div>
                    <div className="font-display font-bold text-foreground">{s.title}</div>
                    <p className="text-xs text-gray-600 dark:text-gray-400">{s.description}</p>
                    <div className="mt-auto flex items-center justify-between">
                      <span className="font-display font-bold text-foreground">
                        ৳{s.price.toLocaleString()}
                        <span className="text-xs font-medium text-gray-500">/{s.unit}</span>
                      </span>
                      <Button
                        asChild
                        size="sm"
                        className="bg-orange-600 text-white hover:bg-orange-700"
                      >
                        <Link to="/dashboard?tab=monetization">Order in dashboard</Link>
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 font-display text-xl font-bold text-foreground">
          <ShieldCheck className="size-5 text-orange-600" /> Renter insurance
        </h2>
        {insuranceLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-36 rounded-2xl" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {insurance.map((p) => (
              <div
                key={p.id}
                className="flex flex-col gap-2 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800"
              >
                <div className="flex items-center justify-between">
                  <div className="font-display font-bold text-foreground">{p.name}</div>
                  <span className="text-xs text-gray-500">{p.partnerName}</span>
                </div>
                <div className="text-sm font-semibold text-foreground">
                  ৳{p.priceMonthly.toLocaleString()}
                  <span className="text-xs font-medium text-gray-500">/month</span>
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
                {!user && (
                  <Button
                    asChild
                    size="sm"
                    className="mt-auto bg-orange-600 text-white hover:bg-orange-700"
                  >
                    <Link to="/auth">Log in to get a quote</Link>
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
        {user && (
          <p className="flex items-center gap-1.5 text-sm text-gray-500">
            <Sparkles className="size-4 text-orange-600" /> Request quotes and manage policies from
            your dashboard.
          </p>
        )}
      </section>
    </div>
  );
}
