import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import ReferralCard from "./ReferralCard";
import referralService from "../../services/referralService";

vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
vi.mock("../../services/referralService", () => ({
  default: { getReferralInfo: vi.fn() },
}));

const referral = {
  code: "ABCD1234",
  link: "http://localhost:3000/auth/register?ref=ABCD1234",
  invitedCount: 2,
  invited: [
    { username: "friend1", joinedAt: "2026-08-01T00:00:00Z" },
    { username: "friend2", joinedAt: "2026-08-02T00:00:00Z" },
  ],
};

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ReferralCard />
    </QueryClientProvider>
  );
}

describe("ReferralCard", () => {
  it("renders the code, invite link and invited count", async () => {
    vi.mocked(referralService.getReferralInfo).mockResolvedValue(referral);
    renderCard();

    expect(await screen.findByText("2 joined")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /copy invite link/i })).toBeInTheDocument();
    expect(screen.getByText(/WhatsApp/)).toBeInTheDocument();
    expect(screen.getByText(/Facebook/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /facebook/i }).getAttribute("href")).toContain(
      encodeURIComponent(referral.link)
    );
  });

  it("copies the link on button click", async () => {
    vi.mocked(referralService.getReferralInfo).mockResolvedValue(referral);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    renderCard();
    const button = await screen.findByRole("button", { name: /copy invite link/i });
    await userEvent.click(button);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(referral.link));
    expect(await screen.findByText(/Copied!/)).toBeInTheDocument();
  });
});
