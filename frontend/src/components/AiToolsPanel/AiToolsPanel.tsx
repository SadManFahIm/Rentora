import { useState } from "react";
import { ClipboardCheck, HandCoins, LifeBuoy, Loader2, Wand2 } from "lucide-react";
import { sendSupportQuestion, type SupportAnswer } from "../../services/copilotService";
import tier4Service, {
  type AgreementCheck,
  type NegotiationDraft,
  type RentalAdvice,
} from "../../services/tier4Service";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

type Tool = "advisor" | "agreement" | "negotiate" | "support";

interface AiToolsPanelProps {
  listingId?: number;
  listingPrice?: number;
  initialTool?: Tool;
}

const TOOLS: { id: Tool; label: string; icon: typeof Wand2 }[] = [
  { id: "advisor", label: "Rental Advisor", icon: Wand2 },
  { id: "agreement", label: "Agreement Checker", icon: ClipboardCheck },
  { id: "negotiate", label: "Negotiation", icon: HandCoins },
  { id: "support", label: "Support", icon: LifeBuoy },
];

/**
 * Tier-4 AI tools — deterministic, data-grounded helpers inside the Copilot
 * widget: budget-based rental advice, agreement clause review, and a
 * negotiation counter-offer draft (EN + BN).
 */
export default function AiToolsPanel({
  listingId,
  listingPrice,
  initialTool = "advisor",
}: AiToolsPanelProps) {
  const [tool, setTool] = useState<Tool>(initialTool);

  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-1 border-b border-gray-100 px-3 py-2 dark:border-gray-800">
        {TOOLS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTool(id)}
            className={cn(
              "inline-flex flex-1 items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-[11px] font-semibold transition",
              tool === id
                ? "bg-orange-500/10 text-orange-600 dark:text-orange-400"
                : "text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
            )}
          >
            <Icon className="size-3.5" />
            {label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {tool === "advisor" && <AdvisorTab />}
        {tool === "agreement" && <AgreementTab />}
        {tool === "negotiate" && <NegotiateTab listingId={listingId} listingPrice={listingPrice} />}
        {tool === "support" && <SupportTab />}
      </div>
    </div>
  );
}

/* -------------------------------- Support -------------------------------- */

function SupportTab() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<SupportAnswer | null>(null);
  const [error, setError] = useState("");

  const run = async () => {
    if (question.trim().length < 3) return;
    setLoading(true);
    setError("");
    try {
      setResult(await sendSupportQuestion(question));
    } catch {
      setError("Couldn't reach support right now — try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3 text-sm">
      <p className="font-semibold text-foreground">Ask the support Copilot</p>
      <textarea
        rows={3}
        placeholder="Ask in Bangla or English — e.g. “ডিপোজিট ফেরত পাব কীভাবে?”"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        aria-label="Support question"
        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-foreground placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500/40 dark:border-gray-600 dark:bg-gray-900"
      />
      <Button
        type="button"
        size="sm"
        onClick={run}
        disabled={loading || question.trim().length < 3}
      >
        {loading ? <Loader2 className="size-3.5 animate-spin" /> : "Get answer"}
      </Button>
      {error && <p className="text-xs text-rose-600">{error}</p>}
      {result && (
        <div className="space-y-2 text-xs">
          <div
            className={cn(
              "rounded-lg px-2.5 py-2 font-semibold",
              result.grounded
                ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                : "bg-amber-500/10 text-amber-700 dark:text-amber-400"
            )}
          >
            {result.grounded ? result.title : `${result.title} (no exact match)`}
          </div>
          <div className="rounded-lg border border-gray-100 p-2.5 dark:border-gray-800">
            <b className="text-foreground">English</b>
            <p className="mt-1 leading-relaxed text-gray-700 dark:text-gray-300">{result.answer}</p>
          </div>
          <div className="rounded-lg border border-gray-100 p-2.5 dark:border-gray-800">
            <b className="text-foreground">বাংলা</b>
            <p className="mt-1 leading-relaxed text-gray-700 dark:text-gray-300">
              {result.answer_bn}
            </p>
          </div>
          {result.grounded && result.matched_keywords && result.matched_keywords.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {result.matched_keywords.slice(0, 3).map((k) => (
                <span
                  key={k}
                  className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                >
                  {k}
                </span>
              ))}
            </div>
          )}
          <p className="text-[10px] text-gray-400">
            {result.grounded
              ? "Answered from the help library — grounded in live platform facts."
              : "No article matched — this is the transparent fallback, not an invented answer."}
          </p>
        </div>
      )}
    </div>
  );
}

/* ---------------------------------- Advisor ------------------------------- */

function AdvisorTab() {
  const [budget, setBudget] = useState("");
  const [income, setIncome] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RentalAdvice | null>(null);
  const [error, setError] = useState("");

  const run = async () => {
    const budgetMax = Number(budget);
    if (!budgetMax || budgetMax <= 0) return;
    setLoading(true);
    setError("");
    try {
      setResult(
        await tier4Service.advisor({
          budget_max: budgetMax,
          monthly_income: income ? Number(income) : null,
        })
      );
    } catch {
      setError("Couldn't get advice right now — try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3 text-sm">
      <div>
        <p className="mb-1 font-semibold text-foreground">Where can I afford?</p>
        <div className="flex gap-2">
          <Input
            type="number"
            min={0}
            placeholder="Monthly budget (৳)"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            aria-label="Monthly budget in taka"
          />
          <Button type="button" size="sm" onClick={run} disabled={loading || !budget}>
            {loading ? <Loader2 className="size-3.5 animate-spin" /> : "Advise"}
          </Button>
        </div>
        <Input
          type="number"
          min={0}
          placeholder="Optional: monthly income (৳)"
          value={income}
          onChange={(e) => setIncome(e.target.value)}
          className="mt-2"
          aria-label="Optional monthly income in taka"
        />
      </div>

      {error && <p className="text-xs text-rose-600">{error}</p>}
      {result && (
        <div className="space-y-2">
          {result.affordability.ratio != null && (
            <div className="rounded-lg bg-gray-50 p-2.5 text-xs dark:bg-gray-800/60">
              <span className="font-semibold text-foreground">
                Rent = {Math.round(result.affordability.ratio * 100)}% of income
              </span>{" "}
              <span className="text-gray-600 dark:text-gray-400">
                ({result.affordability.level}) — {result.affordability.hint}
              </span>
            </div>
          )}
          <ul className="space-y-1.5">
            {result.recommendations.slice(0, 5).map((r) => (
              <li
                key={r.area}
                className="flex items-center justify-between rounded-lg border border-gray-100 px-2.5 py-2 dark:border-gray-800"
              >
                <span className="text-xs text-foreground">
                  <b>{r.area}</b>
                  <span className="block text-[11px] text-gray-500">{r.label}</span>
                </span>
                <span className="text-right text-xs">
                  <b className="text-foreground">
                    {r.median_rent != null ? `৳${r.median_rent.toLocaleString()}` : "n/a"}
                  </b>
                  <span className="block text-[11px] text-gray-500">
                    {r.available_in_budget} in budget
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* -------------------------------- Agreement ------------------------------- */

function AgreementTab() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AgreementCheck | null>(null);
  const [error, setError] = useState("");

  const run = async () => {
    if (text.trim().length < 10) return;
    setLoading(true);
    setError("");
    try {
      setResult(await tier4Service.agreementCheck(text));
    } catch {
      setError("Couldn't check the agreement right now.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3 text-sm">
      <p className="font-semibold text-foreground">Paste your rental agreement</p>
      <textarea
        rows={5}
        placeholder="Paste the agreement text here…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        aria-label="Rental agreement text"
        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-foreground placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-500/40 dark:border-gray-600 dark:bg-gray-900"
      />
      <Button type="button" size="sm" onClick={run} disabled={loading || text.trim().length < 10}>
        {loading ? <Loader2 className="size-3.5 animate-spin" /> : "Check clauses"}
      </Button>
      {error && <p className="text-xs text-rose-600">{error}</p>}
      {result && (
        <div className="space-y-2 text-xs">
          <div
            className={cn(
              "rounded-lg px-2.5 py-2 font-semibold",
              result.verdict === "review"
                ? "bg-amber-500/10 text-amber-700 dark:text-amber-400"
                : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
            )}
          >
            {result.verdict === "review"
              ? "⚠ Review recommended — risky clauses found"
              : "✓ No high-risk clauses detected"}
          </div>
          {result.clauses.map((c) => (
            <div
              key={c.clause}
              className="rounded-lg border border-gray-100 px-2.5 py-2 dark:border-gray-800"
            >
              <b className="capitalize text-foreground">{c.clause.replace("_", " ")}</b>
              <p className="text-gray-600 dark:text-gray-400">{c.explanation}</p>
            </div>
          ))}
          {result.missing.length > 0 && (
            <div className="rounded-lg bg-gray-50 px-2.5 py-2 text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
              <b>Not mentioned — ask the landlord:</b>{" "}
              {result.missing.join(", ").split("_").join(" ")}
            </div>
          )}
          <p className="text-[10px] text-gray-400">{result.disclaimer}</p>
        </div>
      )}
    </div>
  );
}

/* ------------------------------- Negotiation ------------------------------ */

function NegotiateTab({ listingId, listingPrice }: AiToolsPanelProps) {
  const [target, setTarget] = useState("");
  const [role, setRole] = useState<"tenant" | "landlord">("tenant");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<NegotiationDraft | null>(null);
  const [error, setError] = useState("");

  if (!listingId) {
    return (
      <p className="text-xs text-gray-500">
        Open a room&apos;s details and tap <b>“Draft negotiation”</b> to use the negotiation
        assistant.
      </p>
    );
  }

  const run = async () => {
    setLoading(true);
    setError("");
    try {
      setResult(
        await tier4Service.negotiate({
          listing_id: listingId,
          target_price: target ? Number(target) : null,
          role,
        })
      );
    } catch {
      setError("Couldn't draft a message right now.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3 text-sm">
      <p className="font-semibold text-foreground">
        Negotiate this listing{listingPrice ? ` (৳${listingPrice.toLocaleString()}/mo)` : ""}
      </p>
      <div className="flex gap-2">
        <Input
          type="number"
          min={0}
          placeholder="Target price (৳)"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          aria-label="Target price in taka"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as "tenant" | "landlord")}
          className="rounded-lg border border-gray-300 bg-white px-2 text-xs dark:border-gray-600 dark:bg-gray-900"
          aria-label="Your role"
        >
          <option value="tenant">Tenant</option>
          <option value="landlord">Landlord</option>
        </select>
      </div>
      <Button type="button" size="sm" onClick={run} disabled={loading}>
        {loading ? <Loader2 className="size-3.5 animate-spin" /> : "Draft message"}
      </Button>
      {error && <p className="text-xs text-rose-600">{error}</p>}
      {result && (
        <div className="space-y-2 text-xs">
          <div className="rounded-lg bg-gray-50 px-2.5 py-2 dark:bg-gray-800/60">
            <div className="mb-1 flex flex-wrap gap-1.5">
              <span className="rounded-full bg-indigo-500/10 px-2 py-0.5 font-semibold text-indigo-600 dark:text-indigo-400">
                Suggested: ৳{result.suggested_offer.toLocaleString()}
              </span>
              {result.market_median != null && (
                <span className="rounded-full bg-gray-200/60 px-2 py-0.5 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                  Area median: ৳{result.market_median.toLocaleString()}
                </span>
              )}
            </div>
            <p className="text-gray-600 dark:text-gray-400">{result.reason}</p>
          </div>
          <div className="rounded-lg border border-gray-100 p-2.5 dark:border-gray-800">
            <b className="text-foreground">English draft</b>
            <p className="mt-1 leading-relaxed text-gray-700 dark:text-gray-300">
              {result.draft_en}
            </p>
          </div>
          <div className="rounded-lg border border-gray-100 p-2.5 dark:border-gray-800">
            <b className="text-foreground">বাংলা ড্রাফট</b>
            <p className="mt-1 leading-relaxed text-gray-700 dark:text-gray-300">
              {result.draft_bn}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
