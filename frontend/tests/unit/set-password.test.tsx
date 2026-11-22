import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n";

const post = vi.fn();
let token = "tok_0123456789abcdef";
vi.mock("next/navigation", () => ({ useSearchParams: () => ({ get: () => token }), useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/api", () => ({
  api: { post: (...args: unknown[]) => post(...args) },
  ApiError: class ApiError extends Error { status = 400; },
  useApi: () => ({}),
}));

const { SetPasswordForm } = await import("@/components/set-password-form");
const view = (mode: "reset" | "invite" = "reset") =>
  render(<I18nProvider initial="en"><SetPasswordForm mode={mode} /></I18nProvider>);

describe("choosing a password from an emailed link", () => {
  beforeEach(() => { post.mockReset(); token = "tok_0123456789abcdef"; });
  afterEach(cleanup);

  it("needs 12+ characters typed twice the same before it can be saved", () => {
    view();
    const save = screen.getByRole("button", { name: "Save password" });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a-long-passphrase-1" } });
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "a-long-passphrase-2" } });
    expect(screen.getByText("The passwords do not match.")).toBeTruthy();
    expect((save as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Repeat the password"), { target: { value: "a-long-passphrase-1" } });
    expect((save as HTMLButtonElement).disabled).toBe(false);
  });

  it("sends the token with the new password and then offers to sign in", async () => {
    post.mockResolvedValue({ ok: true });
    view("invite");
    expect(screen.getByText("Pick a password to finish joining your team.")).toBeTruthy();
    for (const label of ["New password", "Repeat the password"]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: "a-long-passphrase-1" } });
    }
    fireEvent.click(screen.getByRole("button", { name: "Save password" }));
    await waitFor(() => expect(screen.getByText("Your password is set. You can sign in now.")).toBeTruthy());
    expect(post).toHaveBeenCalledWith("/api/auth/reset-password", { token: "tok_0123456789abcdef", password: "a-long-passphrase-1" });
  });

  it("explains an expired link", async () => {
    post.mockRejectedValue(new Error("400"));
    view();
    for (const label of ["New password", "Repeat the password"]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value: "a-long-passphrase-1" } });
    }
    fireEvent.click(screen.getByRole("button", { name: "Save password" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/invalid or has expired/));
  });

  it("says so when the link has no token", () => {
    token = "";
    view();
    expect(screen.getByRole("alert").textContent).toMatch(/incomplete/);
  });
});
