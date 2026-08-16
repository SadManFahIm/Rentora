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

  it("shows a completed-bookings chip when the tenant has completed stays", () => {
    render(<VerifiedTenantBadge verified completedBookings={3} />);
    expect(screen.getByText("Identity Verified")).toBeInTheDocument();
    expect(screen.getByText("3 completed bookings")).toBeInTheDocument();
  });

  it("shows the singular completed-booking label for one stay", () => {
    render(<VerifiedTenantBadge verified completedBookings={1} />);
    expect(screen.getByText("1 completed booking")).toBeInTheDocument();
  });

  it("omits the completed-bookings chip when the count is zero", () => {
    render(<VerifiedTenantBadge verified completedBookings={0} />);
    expect(screen.queryByText(/completed booking/)).not.toBeInTheDocument();
  });
});
