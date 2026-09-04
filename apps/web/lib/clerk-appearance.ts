/** Shared Clerk `appearance` so sign-in/sign-up/forgot-password match our theme tokens (app/globals.css). */
export const clerkAppearance = {
  variables: {
    colorPrimary: "var(--color-accent)",
    colorBackground: "var(--color-surface-1)",
    colorText: "var(--color-foreground)",
    colorTextSecondary: "var(--color-muted)",
    colorInputBackground: "var(--color-surface-2)",
    colorInputText: "var(--color-foreground)",
    borderRadius: "0.5rem",
  },
  elements: {
    card: "shadow-none border border-border bg-surface-1",
    footerActionLink: "text-accent hover:text-accent/80",
  },
};
