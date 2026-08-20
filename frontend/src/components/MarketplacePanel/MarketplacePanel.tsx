import { useState } from "react";
import { Loader2, Package, Plus, ShoppingBag, Store } from "lucide-react";
import {
  useAddonOrders,
  useAddonServices,
  useCreateAddonOrder,
  useRegisterProvider,
} from "../../hooks/useMarketplace";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Skeleton } from "../ui/skeleton";
import { cn } from "../../lib/utils";

const CATEGORIES = ["cleaning", "relocation", "repairs", "furniture", "utilities", "insurance"];

/** Marketplace panel — add-on services for your stay, order tracking, provider signup. */
export default function MarketplacePanel() {
  const [category, setCategory] = useState<string | undefined>(undefined);
  const { data: services = [], isLoading: servicesLoading } = useAddonServices(category);
  const { data: orders = [] } = useAddonOrders();
  const order = useCreateAddonOrder();
  const register = useRegisterProvider();

  const [qty, setQty] = useState<Record<number, number>>({});
  const [showRegister, setShowRegister] = useState(false);
  const [registerForm, setRegisterForm] = useState({ businessName: "", description: "" });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Store className="size-5 text-orange-600" />
          <div>
            <h2 className="font-display text-lg font-bold text-foreground">
              Add-on services marketplace
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Cleaning, relocation, repairs and more — ordered per stay, powered by verified
              providers.
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={() => setShowRegister((v) => !v)}>
          <Plus className="size-4" /> Register a business
        </Button>
      </div>

      {showRegister && (
        <div className="grid max-w-lg grid-cols-1 gap-3 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
          <Input
            value={registerForm.businessName}
            onChange={(e) => setRegisterForm({ ...registerForm, businessName: e.target.value })}
            placeholder="Business name"
          />
          <Input
            value={registerForm.description}
            onChange={(e) => setRegisterForm({ ...registerForm, description: e.target.value })}
            placeholder="What do you offer?"
          />
          <Button
            className="bg-orange-600 text-white hover:bg-orange-700"
            disabled={register.isPending || !registerForm.businessName.trim()}
            onClick={() =>
              register.mutate(registerForm, {
                onSuccess: () => {
                  setShowRegister(false);
                  setRegisterForm({ businessName: "", description: "" });
                },
              })
            }
          >
            {register.isPending ? <Loader2 className="size-4 animate-spin" /> : null} Submit
          </Button>
        </div>
      )}

      <div className="flex flex-wrap gap-1.5">
        <button
          type="button"
          onClick={() => setCategory(undefined)}
          className={cn(
            "rounded-full px-3.5 py-1.5 text-xs font-semibold transition-colors",
            !category
              ? "bg-orange-600 text-white"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
          )}
        >
          All
        </button>
        {CATEGORIES.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => setCategory(c)}
            className={cn(
              "rounded-full px-3.5 py-1.5 text-xs font-semibold capitalize transition-colors",
              category === c
                ? "bg-orange-600 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
            )}
          >
            {c}
          </button>
        ))}
      </div>

      {servicesLoading ? (
        <div className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full rounded-2xl" />
          ))}
        </div>
      ) : services.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700">
          No services in this category yet.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {services.map((s) => (
            <div
              key={s.id}
              className="flex flex-col gap-2 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800"
            >
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-orange-500/10 px-2 py-0.5 text-[0.65rem] font-bold capitalize text-orange-600">
                  {s.categoryDisplay}
                </span>
                <span className="text-xs text-gray-500">
                  ★ {s.ratingAvg.toFixed(1)} ({s.ratingCount})
                </span>
              </div>
              <div className="font-display font-bold text-foreground">{s.title}</div>
              <p className="text-xs text-gray-600 dark:text-gray-400">{s.description}</p>
              <div className="text-xs text-gray-500">by {s.providerName}</div>
              <div className="mt-auto flex items-center justify-between gap-2">
                <div className="font-display font-bold text-foreground">
                  ৳{s.price.toLocaleString()}
                  <span className="text-xs font-medium text-gray-500">/{s.unit}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <Input
                    type="number"
                    min={1}
                    className="h-8 w-16"
                    value={qty[s.id] ?? 1}
                    onChange={(e) => setQty({ ...qty, [s.id]: Number(e.target.value) })}
                  />
                  <Button
                    size="sm"
                    className="bg-orange-600 text-white hover:bg-orange-700"
                    disabled={order.isPending}
                    onClick={() =>
                      order.mutate({
                        serviceId: s.id,
                        quantity: Math.max(1, qty[s.id] ?? 1),
                      })
                    }
                  >
                    <ShoppingBag className="size-3.5" /> Order
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {orders.length > 0 && (
        <div className="flex flex-col gap-2">
          <h3 className="flex items-center gap-2 font-display font-bold text-foreground">
            <Package className="size-4 text-orange-600" /> My orders
          </h3>
          <div className="overflow-x-auto rounded-2xl border border-gray-200 dark:border-gray-800">
            <table className="w-full min-w-[480px] text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-2.5">Service</th>
                  <th className="px-4 py-2.5">Qty</th>
                  <th className="px-4 py-2.5">Total</th>
                  <th className="px-4 py-2.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {orders.map((o) => (
                  <tr key={o.id}>
                    <td className="px-4 py-2.5 text-foreground">{o.serviceTitle}</td>
                    <td className="px-4 py-2.5 text-gray-500">{o.quantity}</td>
                    <td className="px-4 py-2.5 font-semibold text-foreground">
                      ৳{o.total.toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-semibold capitalize text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                        {o.status}
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
