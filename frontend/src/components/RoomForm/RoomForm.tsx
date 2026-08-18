// Create-listing form (landlord flow) — includes the map LocationPicker so
// every listing gets real coordinates for the geo/map features.
import { useState } from "react";
import { toast } from "sonner";
import { Building2, Loader2, MapPin, Sparkles } from "lucide-react";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import LocationPicker from "../LocationPicker/LocationPicker";
import { useCreateRoom } from "../../hooks/useRooms";
import tier5Service from "../../services/tier5Service";
import { getApiErrorMessage } from "../../services/errors";
import type { RoomType, GenderPref } from "../../types";

const AREAS = ["Dhanmondi", "Mirpur", "Gulshan", "Banani", "Mohammadpur", "Azimpur"];
const AMENITIES = ["WiFi", "AC", "Attached Bath", "Furnished", "Gym", "Parking"];

interface RoomFormProps {
  open: boolean;
  onClose: () => void;
}

export default function RoomForm({ open, onClose }: RoomFormProps) {
  const createRoom = useCreateRoom();
  const [title, setTitle] = useState("");
  const [area, setArea] = useState("Dhanmondi");
  const [type, setType] = useState<RoomType>("Single");
  const [price, setPrice] = useState("");
  const [size, setSize] = useState("");
  const [gender, setGender] = useState<GenderPref>("Any");
  const [amenities, setAmenities] = useState<string[]>([]);
  const [description, setDescription] = useState("");
  const [location, setLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drafting, setDrafting] = useState(false);

  const toggleAmenity = (a: string) =>
    setAmenities((prev) => (prev.includes(a) ? prev.filter((x) => x !== a) : [...prev, a]));

  /** Tier 5: AI draft the listing from the fields filled so far. */
  const handleDraft = async () => {
    setError(null);
    setDrafting(true);
    try {
      const draft = await tier5Service.generateDescription({
        title: title.trim(),
        room_type: type.toLowerCase(),
        price: Number(price) || undefined,
        area,
        size_sqft: Number(size) || undefined,
        gender_preference: gender.toLowerCase(),
        amenities,
      });
      if (!title.trim()) setTitle(draft.title);
      if (!description.trim()) setDescription(draft.description);
      if (amenities.length === 0) setAmenities(draft.amenities);
      toast.success("Draft ready — review and edit before publishing.");
    } catch {
      setError(getApiErrorMessage(new Error(), "Couldn't draft the listing right now."));
    } finally {
      setDrafting(false);
    }
  };

  const handleSubmit = () => {
    setError(null);
    const priceNum = Number(price);
    const sizeNum = Number(size);
    if (!title.trim()) return setError("Title is required.");
    if (!priceNum || priceNum <= 0) return setError("Enter a valid monthly price.");
    if (!sizeNum || sizeNum <= 0) return setError("Enter a valid room size (sqft).");
    if (!location) return setError("Pick a location on the map.");

    createRoom.mutate(
      {
        name: title.trim(),
        type,
        price: priceNum,
        area,
        size: sizeNum,
        gender,
        amenities,
        available: true,
        featured: false,
        tier: "free",
        tierExpiresAt: null,
        // Backend requires a non-blank description and caps coordinates at
        // 9 significant digits (lat/lng are Decimal(9,6)) — the map picker
        // returns full-precision floats, so round to 6 decimals here.
        description: description.trim() || `${title.trim()} in ${area}`,
        lat: Number(location.lat.toFixed(6)),
        lng: Number(location.lng.toFixed(6)),
        owner: "",
        ownerId: null,
        ownerAvatar: "",
        img: "",
        verified: false,
      },
      {
        onSuccess: () => {
          toast.success("Listing created! It's live on the map and in search.");
          onClose();
          // Reset for next time.
          setTitle("");
          setPrice("");
          setSize("");
          setDescription("");
          setAmenities([]);
          setLocation(null);
        },
        onError: (err) => setError(getApiErrorMessage(err, "Could not create the listing.")),
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[92vh] max-w-2xl gap-0 overflow-y-auto rounded-xl p-0 sm:max-w-2xl">
        <div className="flex items-center gap-3 border-b border-gray-100 px-7 py-5 dark:border-gray-800">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-orange-50 text-orange-600 dark:bg-orange-950/40">
            <Building2 className="size-5" />
          </div>
          <div>
            <DialogTitle className="font-display text-xl font-bold">List a Room</DialogTitle>
            <DialogDescription className="text-sm text-gray-500 dark:text-gray-400">
              Pin the exact location — it powers the map view, geo search and price insight.
            </DialogDescription>
          </div>
        </div>

        <div className="grid gap-5 px-7 py-6">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Title *</label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Sunny Studio in Dhanmondi"
            />
          </div>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground">Area *</label>
              <Select value={area} onValueChange={setArea}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AREAS.map((a) => (
                    <SelectItem key={a} value={a}>
                      {a}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground">Type *</label>
              <Select value={type} onValueChange={(v) => setType(v as RoomType)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(["Single", "Shared", "Studio"] as RoomType[]).map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground">
                Gender pref.
              </label>
              <Select value={gender} onValueChange={(v) => setGender(v as GenderPref)}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(["Any", "Male", "Female"] as GenderPref[]).map((g) => (
                    <SelectItem key={g} value={g}>
                      {g}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground">
                Monthly rent (৳) *
              </label>
              <Input
                type="number"
                min={1}
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="12000"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground">
                Size (sqft) *
              </label>
              <Input
                type="number"
                min={1}
                value={size}
                onChange={(e) => setSize(e.target.value)}
                placeholder="350"
              />
            </div>
          </div>

          {/* Location picker — the star of this form */}
          <LocationPicker value={location} onChange={setLocation} label="Listing location *" />

          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Amenities</label>
            <div className="flex flex-wrap gap-2">
              {AMENITIES.map((a) => (
                <button
                  key={a}
                  type="button"
                  onClick={() => toggleAmenity(a)}
                  className={`rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors ${
                    amenities.includes(a)
                      ? "border-orange-500 bg-orange-50 text-orange-700 dark:bg-orange-950/40 dark:text-orange-300"
                      : "border-gray-200 text-gray-600 hover:border-orange-300 dark:border-gray-700 dark:text-gray-400"
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="block text-sm font-medium text-foreground">Description</label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5 text-xs"
                onClick={handleDraft}
                disabled={drafting}
              >
                {drafting ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Sparkles className="size-3.5 text-orange-600" />
                )}
                {drafting ? "Drafting…" : "✨ AI draft"}
              </Button>
            </div>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Tell tenants what makes this room special…"
              className="w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-orange-400 focus:ring-2 focus:ring-orange-500/20 dark:border-gray-700"
            />
          </div>

          {error && (
            <div className="rounded-lg bg-red-50 px-4 py-2.5 text-sm font-medium text-red-600 dark:bg-red-950/40 dark:text-red-400">
              {error}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 border-t border-gray-100 px-7 py-5 dark:border-gray-800">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            className="bg-orange-600 text-white hover:bg-orange-700"
            onClick={handleSubmit}
            disabled={createRoom.isPending}
          >
            {createRoom.isPending ? (
              <>
                <Loader2 className="size-4 animate-spin" /> Creating…
              </>
            ) : (
              <>
                <MapPin className="size-4" /> Publish Listing
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
