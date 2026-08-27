import { describe, expect, it } from "vitest";
import { DHAKA_CENTER, DHAKA_ZOOM, TILE_LIGHT, TILE_DARK, MAP_STYLE } from "./mapConstants";

describe("DHAKA_CENTER", () => {
  it("is in Dhaka, Bangladesh", () => {
    expect(DHAKA_CENTER[0]).toBeGreaterThan(90);
    expect(DHAKA_CENTER[0]).toBeLessThan(91);
    expect(DHAKA_CENTER[1]).toBeGreaterThan(23);
    expect(DHAKA_CENTER[1]).toBeLessThan(24);
  });

  it("is [lng, lat] ordering (MapLibre convention)", () => {
    // Longitude > latitude for Dhaka
    expect(DHAKA_CENTER[0]).toBeGreaterThan(DHAKA_CENTER[1]);
  });
});

describe("DHAKA_ZOOM", () => {
  it("is a reasonable city-level zoom", () => {
    expect(DHAKA_ZOOM).toBeGreaterThanOrEqual(10);
    expect(DHAKA_ZOOM).toBeLessThanOrEqual(13);
  });
});

describe("tile URLs", () => {
  it("LIGHT tiles use OSM", () => {
    expect(TILE_LIGHT).toContain("openstreetmap.org");
  });

  it("DARK tiles use CARTO", () => {
    expect(TILE_DARK).toContain("cartocdn.com");
  });

  it("both have {z}/{x}/{y} placeholders", () => {
    expect(TILE_LIGHT).toContain("{z}");
    expect(TILE_LIGHT).toContain("{x}");
    expect(TILE_LIGHT).toContain("{y}");
    expect(TILE_DARK).toContain("{z}");
    expect(TILE_DARK).toContain("{x}");
    expect(TILE_DARK).toContain("{y}");
  });
});

describe("MAP_STYLE", () => {
  it("returns a valid MapLibre style specification for light mode", () => {
    const style = MAP_STYLE(TILE_LIGHT, "light");
    expect(style.version).toBe(8);
    expect(style.sources.osm.type).toBe("raster");
    expect((style.sources.osm as Record<string, unknown>).tiles).toEqual([TILE_LIGHT]);
    expect(style.layers).toHaveLength(1);
    expect(style.layers[0].id).toBe("osm");
    expect(style.layers[0].type).toBe("raster");
    expect(style.glyphs).toContain("openmaptiles.org");
  });

  it("applies brightness/contrast paint for dark mode", () => {
    const style = MAP_STYLE(TILE_DARK, "dark");
    const paint = (style.layers[0] as Record<string, unknown>).paint as Record<string, number>;
    expect(paint["raster-brightness-min"]).toBe(0.2);
    expect(paint["raster-brightness-max"]).toBe(0.85);
    expect(paint["raster-contrast"]).toBe(0.2);
  });

  it("applies dimmed paint for dark-fallback mode", () => {
    const style = MAP_STYLE(TILE_LIGHT, "dark-fallback");
    const paint = (style.layers[0] as Record<string, unknown>).paint as Record<string, number>;
    expect(paint["raster-brightness-min"]).toBe(0.12);
    expect(paint["raster-saturation"]).toBe(-0.4);
  });

  it("light mode has no special paint (empty object)", () => {
    const style = MAP_STYLE(TILE_LIGHT, "light");
    const paint = (style.layers[0] as Record<string, unknown>).paint;
    expect(paint).toEqual({});
  });
});
