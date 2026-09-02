import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "Amazônika Geoespacial", description: "Sistema de análise territorial e sobreposição de imóveis rurais.", icons:{icon:"/favicon.svg",shortcut:"/favicon.svg"} };
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="pt-BR"><head><meta name="codex-preview" content="development"/></head><body>{children}</body></html>}
