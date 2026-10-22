import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, host: true },
  // mqtt.js alone is ~400 kB; one bundle is fine for a local dashboard.
  build: { chunkSizeWarningLimit: 800 },
  test: {
    environment: "node",
    include: ["src/**/*.test.js"],
  },
});
