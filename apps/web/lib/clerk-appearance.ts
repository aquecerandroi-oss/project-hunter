/**
 * Shared Clerk `appearance` so sign-in/sign-up/forgot-password match our
 * theme tokens (app/globals.css). Gold primary per docs/DESIGN.md §2 --
 * still a single primary action per screen (Clerk's own submit button) --
 * dark surfaces (`bg`/`bg-elevated`) so the auth pages don't flash a white
 * card against our black shell before the theme script even matters.
 */
export const clerkAppearance = {
  variables: {
    colorPrimary: "var(--color-gold)",
    colorBackground: "var(--color-bg-elevated)",
    colorText: "var(--color-fg)",
    colorTextSecondary: "var(--color-fg-muted)",
    colorInputBackground: "var(--color-bg-overlay)",
    colorInputText: "var(--color-fg)",
    colorDanger: "var(--color-red)",
    colorSuccess: "var(--color-green)",
    colorWarning: "var(--color-warning)",
    fontFamily: "var(--font-sans)",
    borderRadius: "0.5rem",
  },
  elements: {
    card: "shadow-none border border-border bg-bg-elevated",
    formButtonPrimary: "bg-gold text-gold-fg hover:bg-gold-strong",
    footerActionLink: "text-gold hover:text-gold-strong",
  },
};
