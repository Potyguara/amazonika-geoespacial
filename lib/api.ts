export function getApiUrl() {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") {
    // Em produção/VPS, o proxy reverso publica /api/v1 no mesmo domínio HTTPS.
    // No desenvolvimento em LAN, a API continua exposta diretamente na porta 8000.
    if (window.location.protocol === "https:") return `${window.location.origin}/api/v1`;
    return `http://${window.location.hostname}:8000/api/v1`;
  }
  return "http://localhost:8000/api/v1";
}
