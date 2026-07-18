import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

export default defineConfig({
  cacheDir: resolve(tmpdir(), `paperwise-vite-${process.pid}`),
  plugins: [react()],
});
