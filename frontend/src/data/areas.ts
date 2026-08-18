/**
 * Area catalogue (Phase 13 — SEO landing pages + sitemap).
 *
 * One entry per Dhaka-area destination served at `/rooms/<slug>`. The `area`
 * field matches the exact `Room.area` string used by the rooms API filter, so
 * an area page queries the real, live listings for that area.
 *
 * `description` powers the page <meta> tag; `keywords` feed a hidden SEO
 * line. Both are short, factual, and not keyword-stuffed.
 */

export interface AreaInfo {
  slug: string;
  area: string;
  title: string;
  description: string;
  keywords: string[];
}

const AREA_DEFS: Omit<AreaInfo, "slug">[] = [
  {
    area: "Dhanmondi",
    title: "Rooms for rent in Dhanmondi, Dhaka",
    description:
      "Rent affordable student rooms, family flats and studios in Dhanmondi, Dhaka — verified listings with real prices, photos and owner contact via Rentora.",
    keywords: ["Dhanmondi room rent", "student room Dhanmondi", "family flat Dhanmondi"],
  },
  {
    area: "Mirpur",
    title: "Rooms for rent in Mirpur, Dhaka",
    description:
      "Find rooms for rent in Mirpur, Dhaka — budget-friendly singles, shared rooms and studios near Mirpur 10 and Mirpur 1. Verified listings with real prices.",
    keywords: ["Mirpur room rent", "Mirpur 10 room", "shared room Mirpur"],
  },
  {
    area: "Gulshan",
    title: "Rooms for rent in Gulshan, Dhaka",
    description:
      "Rooms and studios for rent in Gulshan, Dhaka — premium, verified listings near Gulshan 1 and Gulshan 2 with owner contact, real prices and photos.",
    keywords: ["Gulshan room rent", "studio Gulshan", "flat Gulshan"],
  },
  {
    area: "Banani",
    title: "Rooms for rent in Banani, Dhaka",
    description:
      "Rent a room, studio or apartment in Banani, Dhaka — verified listings near Banani 11 with real prices, photos and direct owner contact on Rentora.",
    keywords: ["Banani room rent", "studio Banani 11", "apartment Banani"],
  },
  {
    area: "Mohammadpur",
    title: "Rooms for rent in Mohammadpur, Dhaka",
    description:
      "Affordable rooms for rent in Mohammadpur, Dhaka — singles, shared rooms and studios for students and bachelors with verified landlords on Rentora.",
    keywords: ["Mohammadpur room rent", "bachelor room Mohammadpur", "student room"],
  },
  {
    area: "Uttara",
    title: "Rooms for rent in Uttara, Dhaka",
    description:
      "Find rooms for rent in Uttara, Dhaka — budget to premium singles, family flats and studios near Uttara Sector 3 to 13 with verified listings.",
    keywords: ["Uttara room rent", "Uttara sector 7 room", "family flat Uttara"],
  },
  {
    area: "Bashundhara",
    title: "Rooms for rent in Bashundhara Residential Area",
    description:
      "Rooms and student studios for rent in Bashundhara Residential Area, Dhaka — near East West University and BRAC University, verified listings only.",
    keywords: ["Bashundhara room rent", "student room Bashundhara", "EWU room"],
  },
  {
    area: "Tejgaon",
    title: "Rooms for rent in Tejgaon, Dhaka",
    description:
      "Rent rooms and studios in Tejgaon, Dhaka — convenient for office-goers near Farmgate and Gulshan. Verified listings with real prices and owner contact.",
    keywords: ["Tejgaon room rent", "studio Tejgaon", "room near Farmgate"],
  },
  {
    area: "Badda",
    title: "Rooms for rent in Badda, Dhaka",
    description:
      "Affordable rooms and studios for rent in Badda, Dhaka — close to Gulshan and Banani. Verified landlords with real prices and photos on Rentora.",
    keywords: ["Badda room rent", "studio Badda", "room near Gulshan"],
  },
  {
    area: "Old Dhaka",
    title: "Rooms for rent in Old Dhaka",
    description:
      "Budget rooms for rent in Old Dhaka (Purana Dhaka) — singles and shared rooms near Kotwali and Sadarghat with verified landlords on Rentora.",
    keywords: ["Old Dhaka room rent", "room Purana Dhaka", "budget room Old Dhaka"],
  },
];

/** Slug helper shared by routes and the sitemap generator. */
export function areaToSlug(area: string): string {
  return area.trim().toLowerCase().replace(/\s+/g, "-");
}

/** The full catalogue (slug derived), excluding "All". */
export const AREAS_INFO: AreaInfo[] = AREA_DEFS.map((def) => ({
  ...def,
  slug: areaToSlug(def.area),
}));

/** Lookup by route slug; undefined for unknown slugs (page 404s gracefully). */
export function getAreaBySlug(slug: string): AreaInfo | undefined {
  return AREAS_INFO.find((a) => a.slug === slug);
}
