import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  build: {
    // backend/main.py zaten backend/web/'i StaticFiles ile /goruntule/ altında
    // sunuyor — build çıktısını doğrudan oraya yazmak backend kodunda hiçbir
    // değişiklik gerektirmiyor.
    outDir: "../backend/web",
    emptyOutDir: true,
  },
  plugins: [react()],
  test: {
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
});
