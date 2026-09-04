// Fast lint tier for PROJECT HUNTER's Next.js app (apps/web). No type
// information here, so it is cheap enough for a pre-commit hook. Type-aware
// rules live in eslint.typed.config.mjs and run as `pnpm lint:types` (CI only).
//
// Consumed from apps/web/eslint.config.mjs as:
//   import { hunterWebConfig } from "@hunter/config/eslint";
//   export default hunterWebConfig({ tsconfigRootDir: import.meta.dirname });
//
// The three quality/* rules come from the vibe-coding-toolkit and are copied
// byte for byte into ./eslint-rules — do not edit them; run ./verify.mjs to
// prove the copy is intact.
import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import { createTypeScriptImportResolver } from "eslint-import-resolver-typescript";
import importX from "eslint-plugin-import-x";
import globals from "globals";
import tseslint from "typescript-eslint";

import quality from "./eslint-rules/index.cjs";

// Framework presets are enabled in M0 (task T08) only after checking the
// installed plugin versions, per the toolkit's advice: presets drift between
// majors, so the exact export name is confirmed against node_modules first.
//   import reactHooks from "eslint-plugin-react-hooks";
//   import nextPlugin from "@next/eslint-plugin-next";

const SOURCE = ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}", "lib/**/*.{ts,tsx}", "hooks/**/*.{ts,tsx}"];
const TESTS = ["**/*.test.{ts,tsx}", "**/{__tests__,__mocks__,fixtures,mocks}/**/*.{ts,tsx}", "tests/**/*.{ts,tsx}"];

export function hunterWebConfig({ tsconfigRootDir, maxLines = 350 } = {}) {
  return defineConfig([
    {
      languageOptions: {
        parserOptions: { tsconfigRootDir },
        globals: { ...globals.browser, ...globals.node },
      },
    },
    js.configs.recommended,
    ...tseslint.configs.strict,
    //   reactHooks.configs.flat.recommended,
    //   nextPlugin.configs["core-web-vitals"],   // confirm export name against installed version

    {
      // Architecture boundary. `lib/server/**` is server-only (Clerk secret,
      // API calls carrying the session token). Client-capable code must never
      // import it — Next.js would otherwise bundle it into the browser.
      plugins: { "import-x": importX, "import-x-debt": importX },
      settings: { "import-x/resolver-next": [createTypeScriptImportResolver()] },
      rules: {
        "import-x/no-unresolved": "error",
        "import-x/no-duplicates": "error",
        "import-x/no-restricted-paths": [
          "error",
          {
            zones: [
              { target: ["./components/**/*", "./hooks/**/*"], from: "./lib/server/**/*" },
              // Client components must not reach the raw WebSocket bridge; go
              // through hooks/useRealtime so throttling and auth stay in one place.
              { target: "./components/**/*", from: "./lib/ws.ts" },
            ],
          },
        ],
        // Aliased second registration for boundaries still being migrated toward.
        // The rule's own schema requires at least one zone (minItems: 1), so an
        // empty list is invalid config, not "no zones yet" -- kept "off" on this
        // greenfield project and flipped to "warn" with a real zone (and its
        // violation count) only when a boundary is introduced over existing code.
        "import-x-debt/no-restricted-paths": "off",
      },
    },
    {
      files: SOURCE,
      plugins: { quality },
      rules: {
        "no-empty": ["error", { allowEmptyCatch: true }],
        "no-var": "error",
        "prefer-const": "error",
        "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
        "@typescript-eslint/consistent-type-imports": ["error", { prefer: "type-imports", fixStyle: "inline-type-imports" }],
        // Size/complexity budget: "warn" on purpose — pressure, not a gate.
        // Promote one to "error" once its count reaches zero.
        complexity: ["warn", 12],
        "max-depth": ["warn", 4],
        "max-statements": ["warn", 20],
        "max-params": ["warn", 4],
        "max-lines-per-function": ["warn", { max: 150, skipBlankLines: true, skipComments: true }],
        "max-nested-callbacks": ["warn", 3],
        // Whole-file ceiling is a hard stop. Greenfield project → zero
        // violations → born at "error". Never raise `max` to make a file pass;
        // list a known offender in `ignore` instead.
        "quality/max-lines": ["error", { max: maxLines, ignore: [] }],
        "quality/no-direct-console": ["error", { logger: "@/lib/logger" }],
        "quality/no-direct-data-access": [
          "error",
          {
            modules: ["@/lib/server/api", "@/lib/server/auth", "@/lib/server"],
            bindings: ["apiFetch", "serverApi", "getServerSession"],
            layers: ["/components/", "/hooks/"],
            extensions: [],
          },
        ],
      },
    },
    {
      // The log adapter itself and Next.js instrumentation may touch console.
      // Must come AFTER the block that turns the rule on.
      files: ["lib/logger.ts", "instrumentation.ts", "instrumentation-client.ts"],
      rules: { "quality/no-direct-console": "off" },
    },
    {
      files: TESTS,
      plugins: { quality },
      rules: {
        "quality/max-lines": ["warn", { max: maxLines, includeTests: true }],
        "max-statements": "off",
        "max-lines-per-function": "off",
        "max-nested-callbacks": "off",
        "import-x/no-restricted-paths": "off",
        "import-x-debt/no-restricted-paths": "off",
      },
    },
    {
      files: ["**/eslint-rules/**/*.cjs"],
      languageOptions: { sourceType: "commonjs", globals: { module: "readonly", require: "readonly" } },
      rules: { "@typescript-eslint/no-require-imports": "off" },
    },
    globalIgnores([
      ".claude/**",
      ".next/**",
      "out/**",
      "node_modules/**",
      "dist/**",
      "build/**",
      "coverage/**",
      "playwright-report/**",
      "test-results/**",
      "**/*.tsbuildinfo",
      "next-env.d.ts",
      // generated from the FastAPI OpenAPI document
      "../../packages/shared-types/src/generated/**",
    ]),
  ]);
}

export default hunterWebConfig();
