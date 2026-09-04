// Fast lint tier for @hunter/web. See packages/config/README.md for the
// two-tier rationale (this tier is the pre-commit/CI-fast one).
import { hunterWebConfig } from "@hunter/config/eslint";

export default hunterWebConfig({ tsconfigRootDir: import.meta.dirname });
