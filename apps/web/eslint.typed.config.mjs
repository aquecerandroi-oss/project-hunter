// Type-aware lint tier (`pnpm lint:types`, CI only). See
// packages/config/eslint/eslint.typed.config.mjs for why this stays a
// separate config/script instead of branching on process.env.CI.
import typedConfig from "@hunter/config/eslint/typed";

export default typedConfig;
