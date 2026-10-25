export function getApiUrl() {
  if (typeof window !== "undefined") {
    // Desenvolvimento local usa o proxy /api do Vite: requests de tiles,
    // imagens e fetch compartilham a sessão/cookie do frontend.
    if (window.location.protocol === "http:" && window.location.port === "3000") {
      return `${window.location.origin}/api/v1`;
    }
  }

  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") {
    if (window.location.protocol === "https:") return `${window.location.origin}/api/v1`;
    return `http://${window.location.hostname}:8000/api/v1`;
  }
  return "http://localhost:8000/api/v1";
}
