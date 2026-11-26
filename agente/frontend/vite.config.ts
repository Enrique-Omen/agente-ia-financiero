import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// La clave de la API vive en el archivo de entorno del servidor (sin prefijo VITE_) y solo la lee este proxy:
// nunca entra al paquete JS que baja el navegador.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxy = {
    "/api": {
      target: env.BACKEND_URL || "http://127.0.0.1:8765",
      rewrite: (p: string) => p.replace(/^\/api/, ""),
      headers: { "X-API-Key": env.AGENTE_API_KEY || "" },
    },
  };
  return { plugins: [react()], server: { proxy }, preview: { proxy } };
});
