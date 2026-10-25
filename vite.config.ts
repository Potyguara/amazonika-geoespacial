import vinext from "vinext";
import { defineConfig } from "vite";

// Configuração reproduzível para desenvolvimento local e build da VPS.
// O projeto não usa bindings D1/R2; portanto, plugins gerados por ambientes
// externos não podem ser dependência obrigatória de um clone Git limpo.
const isCodexSeatbeltSandbox = process.env.CODEX_SANDBOX === "seatbelt";

export default defineConfig({
  server: {
    host: "0.0.0.0",
    allowedHosts: ["localhost", "127.0.0.1", "terminal.local"],
    // Na homologação, API e tiles MVT ficam na mesma origem do navegador.
    // Dessa forma os cookies HttpOnly acompanham os requests do OpenLayers.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
    ...(isCodexSeatbeltSandbox
      ? { watch: { useFsEvents: false, usePolling: true } }
      : {}),
  },
  plugins: [vinext()],
});
