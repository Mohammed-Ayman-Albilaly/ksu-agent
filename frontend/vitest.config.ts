import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The front end is Next.js, but the components under test are plain React, so Vite can
// render them in jsdom. The "@" alias mirrors tsconfig's paths, and the JSX runtime is
// named here because tsconfig keeps "jsx": "preserve" for Next.
export default defineConfig({
  plugins: [react({ jsxRuntime: "automatic" })],
  esbuild: { jsx: "automatic" },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    // jsdom gives a document an opaque origin (about:blank) unless a URL is set, and an
    // opaque origin has no localStorage: every test that touches web storage failed on
    // window.localStorage.clear() before this was named here.
    environmentOptions: { jsdom: { url: "http://localhost:3000" } },
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
