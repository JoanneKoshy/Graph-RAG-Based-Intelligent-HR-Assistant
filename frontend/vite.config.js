import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development, calls to /api go to the Python API on port 8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
