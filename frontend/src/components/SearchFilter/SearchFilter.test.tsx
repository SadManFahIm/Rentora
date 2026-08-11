import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import SearchFilter from "./SearchFilter";
import type { Filters } from "../../types";

const baseFilters: Filters = {
  query: "",
  area: "All",
  type: "All",
  sort: "default",
  amenities: [],
  gender: "Any",
  available: "any",
  minPrice: "",
  maxPrice: "",
  verified: false,
};

describe("SearchFilter — AI smart search", () => {
  it("toggles smart mode and switches the placeholder to a natural-language hint", async () => {
    const user = userEvent.setup();
    const setFilters = vi.fn();
    const { rerender } = render(<SearchFilter filters={baseFilters} setFilters={setFilters} />);

    // Off by default: normal placeholder, no AI badge.
    expect(screen.getByPlaceholderText("Search by name or area...")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /ai search/i }));
    expect(setFilters).toHaveBeenCalledWith(expect.any(Function));

    // Flip on -> Bangla example placeholder.
    rerender(<SearchFilter filters={{ ...baseFilters, smart: true }} setFilters={setFilters} />);
    expect(screen.getByPlaceholderText(/১০ হাজার এর মধ্যে uttara/)).toBeInTheDocument();
    expect(screen.getByText("AI")).toBeInTheDocument();

    // Flip back off.
    await user.click(screen.getByRole("button", { name: /ai search/i }));
    expect(setFilters).toHaveBeenCalled();
  });
});
