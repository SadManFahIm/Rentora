import { describe, expect, it } from "vitest";
import { AREAS_INFO, areaToSlug, getAreaBySlug } from "./areas";

describe("areas catalogue", () => {
  it("derives lower-case hyphenated slugs", () => {
    expect(areaToSlug("Old Dhaka")).toBe("old-dhaka");
    expect(areaToSlug("Dhanmondi")).toBe("dhanmondi");
  });

  it("maps every area to a unique route slug", () => {
    const slugs = AREAS_INFO.map((a) => a.slug);
    expect(new Set(slugs).size).toBe(AREAS_INFO.length);
  });

  it("returns the area for a known slug", () => {
    const area = getAreaBySlug("bashundhara");
    expect(area?.area).toBe("Bashundhara");
    expect(area?.title).toContain("Bashundhara");
  });

  it("returns undefined for unknown slugs", () => {
    expect(getAreaBySlug("narnia")).toBeUndefined();
  });

  it("gives every area SEO copy (title + description + keywords)", () => {
    for (const area of AREAS_INFO) {
      expect(area.title.length).toBeGreaterThan(10);
      expect(area.description.length).toBeGreaterThan(40);
      expect(area.keywords.length).toBeGreaterThan(0);
    }
  });
});
