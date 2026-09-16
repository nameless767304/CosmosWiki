import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // Flags standard fetch-on-mount / refetch-on-prop-change effects as
      // errors; every occurrence in this codebase is that intentional
      // pattern, not a derived-state bug the rule is meant to catch.
      "react-hooks/set-state-in-effect": "off",
      // Allow an explicit `_`-prefixed binding to mark an intentionally
      // unused variable, e.g. destructuring away react-markdown's `node`.
      "@typescript-eslint/no-unused-vars": ["warn", { "varsIgnorePattern": "^_", "argsIgnorePattern": "^_" }],
    },
  },
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
