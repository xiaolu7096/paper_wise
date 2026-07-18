import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    exclude: ["tests/e2e/**", "node_modules/**", "dist/**"],
    passWithNoTests: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
