import { describe, expect, it } from "vitest";
import { buildListingShareText, buildWhatsAppShareText, whatsappShareUrl } from "./share";

describe("whatsappShareUrl", () => {
  it("builds a wa.me link with an encoded body", () => {
    const url = whatsappShareUrl("Hello there & thanks!");
    expect(url).toBe("https://wa.me/?text=Hello%20there%20%26%20thanks!");
  });
});

describe("buildListingShareText", () => {
  const room = {
    id: 1,
    name: "Bright Studio, Dhanmondi",
    price: 14000,
    area: "Dhanmondi",
    type: "Studio",
    amenities: ["WiFi", "Furnished", "Attached Bath"],
    verified: true,
  };

  it("includes the real price, area and title", () => {
    const text = buildListingShareText(room);
    expect(text).toContain("Bright Studio, Dhanmondi");
    expect(text).toContain("14,000");
    expect(text).toContain("Dhanmondi");
  });

  it("lists real amenities and the verified flag", () => {
    const text = buildListingShareText(room);
    expect(text).toContain("WiFi");
    expect(text).toContain("Furnished");
    expect(text).toContain("verified");
  });

  it("omits verification when the room is unverified", () => {
    const text = buildListingShareText({ ...room, verified: false });
    expect(text.toLowerCase()).not.toContain("verified");
  });
});

describe("buildWhatsAppShareText", () => {
  it("appends the shareable room link", () => {
    const text = buildWhatsAppShareText("Bright Studio — Dhanmondi · ৳14,000", {
      id: 1,
      name: "Bright Studio, Dhanmondi",
      area: "Dhanmondi",
    });
    expect(text).toContain("Bright Studio — Dhanmondi · ৳14,000");
    expect(text).toContain("Check it on Rentora");
    expect(text).toContain("/rooms/dhanmondi?room=1");
  });
});
