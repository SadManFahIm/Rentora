import { useEffect, useState } from "react";
import { isAuthenticated } from "../../services/api";
import {
  useRespondRoommateRequest,
  useRoommateMatches,
  useRoommateProfile,
  useRoommateRequests,
  useSaveRoommateProfile,
  useSendRoommateRequest,
} from "../../hooks/useRoommates";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Badge } from "../../components/ui/badge";
import { cn } from "../../lib/utils";
import type { LifestyleTag, RoommateProfilePayload } from "../../types";

// ============================================================
// ROOMMATES — find someone to share rent with
// ============================================================

const AREAS = ["Dhanmondi", "Mirpur", "Gulshan", "Banani", "Mohammadpur", "Azimpur"];
const ROOM_TYPES = ["single", "shared", "studio"];
const GENDER_PREFS = ["any", "male", "female"];
const LIFESTYLE_OPTIONS: LifestyleTag[] = [
  "early_bird",
  "night_owl",
  "non_smoker",
  "smoker",
  "student",
  "working_professional",
  "quiet",
  "social",
  "veggie",
  "pet_friendly",
  "clean",
  "guest_friendly",
];

const lifestyleLabel = (tag: string): string =>
  tag.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

const emptyProfile: RoommateProfilePayload = {
  budgetMin: 5000,
  budgetMax: 10000,
  preferredArea: "Dhanmondi",
  roomTypePref: "shared",
  genderPref: "any",
  lifestyle: [],
  occupation: "",
  bio: "",
  moveInDate: null,
  isLooking: true,
};

function ProfileForm({
  initial,
  onSaved,
}: {
  initial: RoommateProfilePayload;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<RoommateProfilePayload>(initial);
  const saveProfile = useSaveRoommateProfile();

  const set = <K extends keyof RoommateProfilePayload>(key: K, value: RoommateProfilePayload[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const toggleLifestyle = (tag: LifestyleTag) =>
    setForm((f) => ({
      ...f,
      lifestyle: f.lifestyle.includes(tag)
        ? f.lifestyle.filter((t) => t !== tag)
        : [...f.lifestyle, tag],
    }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    saveProfile.mutate(form, { onSuccess: onSaved });
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-2xl border border-gray-200 bg-card p-6 dark:border-gray-800"
    >
      <h2 className="mb-1 font-display text-lg font-bold text-foreground">
        Set up your roommate profile
      </h2>
      <p className="mb-5 text-sm text-gray-600 dark:text-gray-400">
        Tell us your budget, preferred area and lifestyle so we can match you with the right person.
      </p>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-foreground">
            Budget (৳/month)
          </label>
          <div className="flex items-center gap-2">
            <Input
              type="number"
              min={0}
              value={form.budgetMin}
              onChange={(e) => set("budgetMin", Number(e.target.value))}
              aria-label="Minimum budget"
            />
            <span className="text-gray-500">–</span>
            <Input
              type="number"
              min={0}
              value={form.budgetMax}
              onChange={(e) => set("budgetMax", Number(e.target.value))}
              aria-label="Maximum budget"
            />
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-foreground">Preferred area</label>
          <select
            value={form.preferredArea}
            onChange={(e) => set("preferredArea", e.target.value)}
            className="h-10 w-full rounded-xl border border-gray-300 bg-transparent px-3 text-sm text-foreground outline-none focus:border-brand dark:border-gray-700"
          >
            {AREAS.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-foreground">Room type</label>
          <div className="flex gap-2">
            {ROOM_TYPES.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => set("roomTypePref", t)}
                className={cn(
                  "flex-1 rounded-xl border px-3 py-2 text-sm font-medium capitalize transition-colors",
                  form.roomTypePref === t
                    ? "border-orange-600 bg-orange-50 text-orange-600 dark:bg-orange-950/40 dark:text-orange-400"
                    : "border-gray-200 text-gray-600 hover:border-gray-300 dark:border-gray-800 dark:text-gray-400"
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-foreground">
            Roommate gender preference
          </label>
          <div className="flex gap-2">
            {GENDER_PREFS.map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => set("genderPref", g)}
                className={cn(
                  "flex-1 rounded-xl border px-3 py-2 text-sm font-medium capitalize transition-colors",
                  form.genderPref === g
                    ? "border-orange-600 bg-orange-50 text-orange-600 dark:bg-orange-950/40 dark:text-orange-400"
                    : "border-gray-200 text-gray-600 hover:border-gray-300 dark:border-gray-800 dark:text-gray-400"
                )}
              >
                {g}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-foreground">Occupation</label>
          <Input
            value={form.occupation}
            onChange={(e) => set("occupation", e.target.value)}
            placeholder="e.g. University Student"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-foreground">Move-in date</label>
          <Input
            type="date"
            value={form.moveInDate ?? ""}
            onChange={(e) => set("moveInDate", e.target.value || null)}
          />
        </div>
      </div>

      <div className="mt-4">
        <label className="mb-2 block text-sm font-medium text-foreground">Lifestyle tags</label>
        <div className="flex flex-wrap gap-2">
          {LIFESTYLE_OPTIONS.map((tag) => (
            <button
              key={tag}
              type="button"
              onClick={() => toggleLifestyle(tag)}
              className={cn(
                "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                form.lifestyle.includes(tag)
                  ? "border-orange-600 bg-orange-50 text-orange-600 dark:bg-orange-950/40 dark:text-orange-400"
                  : "border-gray-200 text-gray-600 hover:border-gray-300 dark:border-gray-800 dark:text-gray-400"
              )}
            >
              {lifestyleLabel(tag)}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4">
        <label className="mb-1.5 block text-sm font-medium text-foreground">About you</label>
        <textarea
          value={form.bio}
          onChange={(e) => set("bio", e.target.value)}
          rows={3}
          placeholder="A few lines about yourself and what you're looking for…"
          className="w-full rounded-xl border border-gray-300 bg-transparent px-3 py-2 text-sm text-foreground outline-none focus:border-brand dark:border-gray-700"
        />
      </div>

      <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
        <input
          type="checkbox"
          checked={form.isLooking}
          onChange={(e) => set("isLooking", e.target.checked)}
          className="size-4 accent-orange-600"
        />
        Actively looking for a roommate
      </label>

      <Button
        type="submit"
        className="mt-5 bg-orange-600 text-white hover:bg-orange-700"
        disabled={saveProfile.isPending}
      >
        {saveProfile.isPending ? "Saving…" : "Save profile"}
      </Button>
    </form>
  );
}

function MatchCard({
  match,
  disabled,
  onRequest,
}: {
  match: {
    score: number;
    reasons: string[];
    profile: {
      username: string;
      user: { first_name: string; last_name: string; nid_verified: boolean };
      preferredArea: string;
      roomTypePref: string;
      occupation: string;
      bio: string;
      lifestyle: string[];
      budgetMin: number;
      budgetMax: number;
    };
  };
  disabled: boolean;
  onRequest: () => void;
}) {
  const name =
    [match.profile.user.first_name, match.profile.user.last_name].filter(Boolean).join(" ") ||
    match.profile.username;
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0])
    .join("")
    .toUpperCase();

  return (
    <div className="flex flex-col rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
      <div className="mb-3 flex items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-orange-500 to-orange-700 text-sm font-bold text-white">
          {initials}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h4 className="truncate font-display text-sm font-bold text-foreground">{name}</h4>
            {match.profile.user.nid_verified && <Badge variant="brand">✓ Verified</Badge>}
          </div>
          <p className="truncate text-xs text-gray-600 dark:text-gray-400">
            {match.profile.occupation || match.profile.username} • {match.profile.preferredArea} •{" "}
            {match.profile.roomTypePref}
          </p>
        </div>
      </div>

      <div className="mb-3">
        <div className="mb-1 flex items-center justify-between text-sm">
          <span className="text-gray-600 dark:text-gray-400">Match</span>
          <span className="font-display font-bold text-orange-600 dark:text-orange-400">
            {match.score}%
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700">
          <div
            className="h-full rounded-full bg-gradient-to-r from-orange-500 to-orange-600"
            style={{ width: `${match.score}%` }}
          />
        </div>
      </div>

      <p className="mb-2 text-xs leading-relaxed text-gray-600 dark:text-gray-400">
        ৳{match.profile.budgetMin.toLocaleString()}–{match.profile.budgetMax.toLocaleString()}/mo
      </p>

      {match.profile.bio && (
        <p className="mb-3 text-sm leading-relaxed text-gray-700 dark:text-gray-300">
          “{match.profile.bio}”
        </p>
      )}

      {match.profile.lifestyle.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {match.profile.lifestyle.map((tag) => (
            <span
              key={tag}
              className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-400"
            >
              {lifestyleLabel(tag)}
            </span>
          ))}
        </div>
      )}

      {match.reasons.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {match.reasons.map((reason) => (
            <span
              key={reason}
              className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-400"
            >
              {reason}
            </span>
          ))}
        </div>
      )}

      <Button
        className="mt-auto bg-orange-600 text-white hover:bg-orange-700"
        onClick={onRequest}
        disabled={disabled}
      >
        {disabled ? "Request sent" : "Request roommate"}
      </Button>
    </div>
  );
}

function RequestsSection() {
  const { data: requests = [] } = useRoommateRequests(true);
  const respond = useRespondRoommateRequest();

  const incoming = requests.filter((r) => r.direction === "incoming" && r.status === "pending");
  const outgoing = requests.filter((r) => r.direction === "outgoing");
  const others = requests.filter((r) => r.direction === "incoming" && r.status !== "pending");

  const nameOf = (u: { first_name: string; last_name: string; username: string }) =>
    [u.first_name, u.last_name].filter(Boolean).join(" ") || u.username;

  if (requests.length === 0) return null;

  return (
    <div className="mt-10">
      <h2 className="mb-4 font-display text-lg font-bold text-foreground">Roommate requests</h2>

      {incoming.length > 0 && (
        <div className="mb-5">
          <h3 className="mb-2 text-sm font-semibold text-gray-600 dark:text-gray-400">Incoming</h3>
          <div className="flex flex-col gap-2">
            {incoming.map((r) => (
              <div
                key={r.id}
                className="flex flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50/40 p-4 dark:border-amber-900/40 dark:bg-amber-950/10 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <div className="text-sm font-semibold text-foreground">
                    {nameOf(r.sender)} wants to share a room
                  </div>
                  {r.message && (
                    <p className="mt-0.5 text-xs text-gray-600 dark:text-gray-400">“{r.message}”</p>
                  )}
                </div>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    className="bg-emerald-600 text-white hover:bg-emerald-700"
                    onClick={() => respond.mutate({ requestId: r.id, action: "approve" })}
                    disabled={respond.isPending}
                  >
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => respond.mutate({ requestId: r.id, action: "reject" })}
                    disabled={respond.isPending}
                  >
                    Reject
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {outgoing.length > 0 && (
        <div className="mb-5">
          <h3 className="mb-2 text-sm font-semibold text-gray-600 dark:text-gray-400">Outgoing</h3>
          <div className="flex flex-col gap-2">
            {outgoing.map((r) => (
              <div
                key={r.id}
                className="flex items-center justify-between rounded-xl border border-gray-200 bg-card p-4 dark:border-gray-800"
              >
                <div className="text-sm text-gray-700 dark:text-gray-300">
                  Requested{" "}
                  <span className="font-semibold text-foreground">{nameOf(r.receiver)}</span>
                </div>
                <Badge
                  className={cn(
                    r.status === "pending" && "bg-amber-500/10 text-amber-500",
                    r.status === "approved" && "bg-emerald-500/10 text-emerald-500",
                    r.status === "rejected" && "bg-red-500/10 text-red-500"
                  )}
                >
                  {r.statusDisplay}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {others.length > 0 && (
        <div className="flex flex-col gap-2">
          {others.map((r) => (
            <div
              key={r.id}
              className="flex items-center justify-between rounded-xl border border-gray-200 bg-card p-4 dark:border-gray-800"
            >
              <div className="text-sm text-gray-700 dark:text-gray-300">
                {nameOf(r.sender)}'s request —{" "}
                <span className="font-semibold">{r.statusDisplay}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Roommates() {
  // Token-based check (not context): the page reads only authenticated API
  // endpoints, so a valid stored token is the right gate — and it survives
  // a page reload where the in-memory context user would not.
  const loggedIn = isAuthenticated();
  const { data: profile, isLoading: profileLoading } = useRoommateProfile();
  const [showForm, setShowForm] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);

  const hasProfile = !!profile;
  const matches = useRoommateMatches(hasProfile && loggedIn);
  const sendRequest = useSendRoommateRequest();

  const currentInitial: RoommateProfilePayload = profile
    ? {
        budgetMin: profile.budgetMin,
        budgetMax: profile.budgetMax,
        preferredArea: profile.preferredArea,
        roomTypePref: profile.roomTypePref,
        genderPref: profile.genderPref,
        lifestyle: profile.lifestyle,
        occupation: profile.occupation,
        bio: profile.bio,
        moveInDate: profile.moveInDate,
        isLooking: profile.isLooking,
      }
    : emptyProfile;

  // Re-enable the form after a fresh profile save.
  useEffect(() => {
    if (profile && showForm) setShowForm(false);
  }, [profile, showForm]);

  if (!loggedIn) {
    return (
      <div className="mx-auto flex max-w-7xl flex-col items-center px-4 py-20 text-center md:px-6 lg:px-8">
        <span className="mb-4 text-6xl">👥</span>
        <h1 className="mb-2 font-display text-2xl font-bold text-foreground">Find a roommate</h1>
        <p className="mb-6 max-w-md text-gray-600 dark:text-gray-400">
          Split the rent and find someone who matches your budget, area and lifestyle. Sign in to
          get started.
        </p>
        <Button className="bg-orange-600 text-white hover:bg-orange-700">
          Sign in to continue
        </Button>
      </div>
    );
  }

  if (profileLoading) {
    return <div className="py-20 text-center text-gray-600 dark:text-gray-400">Loading…</div>;
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-12 md:px-6 md:py-16 lg:px-8">
      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-foreground">Find a roommate</h1>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            {hasProfile
              ? `Looking in ${profile!.preferredArea} • ৳${profile!.budgetMin.toLocaleString()}–${profile!.budgetMax.toLocaleString()}/mo`
              : "Set up your profile to see matches."}
          </p>
        </div>
        {hasProfile && (
          <Button variant="outline" onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Hide form" : "Edit profile"}
          </Button>
        )}
      </div>

      {(!hasProfile || showForm) && (
        <ProfileForm initial={currentInitial} onSaved={() => setShowForm(false)} />
      )}

      {hasProfile && !showForm && (
        <>
          {matches.isLoading ? (
            <div className="py-15 text-center text-gray-600 dark:text-gray-400">
              Finding your best matches…
            </div>
          ) : matches.data && matches.data.length > 0 ? (
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {matches.data.map((m) => (
                <MatchCard
                  key={m.profile.id}
                  match={m}
                  disabled={selectedUserId === m.profile.user.id}
                  onRequest={() => {
                    setSelectedUserId(m.profile.user.id);
                    sendRequest.mutate({
                      receiverId: m.profile.user.id,
                      message: "Hi! Saw we're both looking in the same area. Want to share a room?",
                    });
                  }}
                />
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center px-5 py-15 text-center text-gray-600 dark:text-gray-400">
              <span className="mb-4 text-5xl">🔍</span>
              <h3 className="mb-2 font-display text-lg font-bold text-foreground">
                No matches yet
              </h3>
              <p className="max-w-sm">
                Try widening your budget or choosing a more common area. New profiles appear here as
                people join.
              </p>
            </div>
          )}

          <RequestsSection />
        </>
      )}

      {!hasProfile && (
        <div className="mt-6 text-center text-xs text-gray-500 dark:text-gray-500">
          Your matches and requests will appear here once your profile is saved.
        </div>
      )}
    </div>
  );
}
