import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import VerifiedTenantBadge from "./VerifiedTenantBadge";

describe("VerifiedTenantBadge", () => {
  it("renders the Identity Verified badge when verified", () => {
    render(<VerifiedTenantBadge verified />);
    const badge = screen.getByLabelText("Identity verified tenant");
    expect(badge).toBeInTheDocument();
    expect(screen.getByText("Identity Verified")).toBeInTheDocument();
    // The tooltip says exactly what the badge means — never more.
    expect(badge).toHaveAttribute("title", "Identity verified by Rentora.");
  });

  it("renders nothing when not verified by default", () => {
    const { container } = render(<VerifiedTenantBadge verified={false} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a muted Not verified chip when showUnverified is set", () => {
    render(<VerifiedTenantBadge verified={false} showUnverified />);
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(screen.queryByText("Identity Verified")).not.toBeInTheDocument();
  });
});
