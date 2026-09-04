// Type-aware lint tier, deliberately kept OUT of eslint.config.mjs. Turning
// on projectService means ESLint builds a full TypeScript program, which on
// a large codebase is slow enough to break a pre-commit hook and heavy
// enough to exhaust the heap on a small CI runner.
//
// Two config files and two npm scripts (`lint` and `lint:types`), rather
// than one config branching on process.env.CI: branching makes local and CI
// behavior diverge silently for identical code, and reading process.env
// inside a flat config file trips that config's own no-undef rule.
//
// A factory, like the fast tier's `hunterWebConfig`: `import.meta.dirname`
// here would resolve to this file's own directory (packages/config/eslint),
// not the consuming app's, so `tsconfigRootDir` must come from the caller.
import { hunterWebConfig } from "./eslint.config.mjs";

export function hunterWebTypedConfig({ tsconfigRootDir } = {}) {
  return [
    ...hunterWebConfig({ tsconfigRootDir }),
    {
      files: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}", "lib/**/*.{ts,tsx}", "hooks/**/*.{ts,tsx}"],
      languageOptions: {
        parserOptions: {
          projectService: true,
          tsconfigRootDir,
        },
      },
      rules: {
        // Every rule here starts at "warn". None of them has a known violation
        // count on a codebase this config has never run against, so none of
        // them gets to fail a build sight unseen. Promote to "error" per rule,
        // once its count is zero.
        "@typescript-eslint/no-floating-promises": "warn",
        "@typescript-eslint/no-misused-promises": "warn",
        "@typescript-eslint/no-unsafe-assignment": "warn",
        "@typescript-eslint/no-unsafe-member-access": "warn",
        "@typescript-eslint/no-unsafe-call": "warn",
        "@typescript-eslint/no-unsafe-return": "warn",
        "@typescript-eslint/no-unsafe-argument": "warn",
        "@typescript-eslint/only-throw-error": "warn",
        "@typescript-eslint/return-await": ["warn", "in-try-catch"],
        "@typescript-eslint/await-thenable": "warn",
        "@typescript-eslint/unbound-method": "warn",
        "@typescript-eslint/restrict-template-expressions": "warn",
        "@typescript-eslint/restrict-plus-operands": "warn",
        "@typescript-eslint/require-await": "warn",
      },
    },
  ];
}

// Backwards compatibility for anything importing the default export directly
// (`tsconfigRootDir` then falls back to this package's own directory, which
// is wrong for a consumer — callers should use the named factory instead).
export default hunterWebTypedConfig();
