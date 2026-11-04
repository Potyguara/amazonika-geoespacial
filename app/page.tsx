"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { GeoMap } from "@/components/geo-map";
import { SigefModule, SourceVersion } from "@/components/sigef-module";
import { SourcesModule } from "@/components/sources-module";
import { UsersModule } from "@/components/users-module";
import { SettingsModule } from "@/components/settings-module";
import { ThematicMapsModule } from "@/components/thematic-maps-module";
import { ProfessionalProfile } from "@/components/professional-profile";
import { AnalysesModule } from "@/components/analyses-module";
import { TechnicalPiecesModule, type TechnicalPieceSnapshot } from "@/components/technical-pieces-module";
import { getApiUrl } from "@/lib/api";
import {
  Activity,
  Database,
  Eye,
  EyeOff,
  ChevronDown,
  ChevronUp,
  FileSearch,
  FileText,
  Layers3,
  LockKeyhole,
  LogOut,
  Map,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  ScanSearch,
  Search,
  Settings,
  ShieldCheck,
  UploadCloud,
  Users,
  X,
} from "lucide-react";

const API_URL = getApiUrl();

type CatalogLayer = {
  id?: string;
  slug?: string;
  name: string;
  source: string;
  color: string;
  active: boolean;
  wmsEnabled?: boolean;
  wmsTheme?: string;
  wmsFixedLayer?: string;
  wmsGlobal?: boolean;
  wmsAvailableUfs?: string[];
  scopeUf?: string;
};

const BRAZIL_STATES = [
  { value: "AC", label: "AC - Acre" },
  { value: "AL", label: "AL - Alagoas" },
  { value: "AP", label: "AP - Amapá" },
  { value: "AM", label: "AM - Amazonas" },
  { value: "BA", label: "BA - Bahia" },
  { value: "CE", label: "CE - Ceará" },
  { value: "DF", label: "DF - Distrito Federal" },
  { value: "ES", label: "ES - Espírito Santo" },
  { value: "GO", label: "GO - Goiás" },
  { value: "MA", label: "MA - Maranhão" },
  { value: "MT", label: "MT - Mato Grosso" },
  { value: "MS", label: "MS - Mato Grosso do Sul" },
  { value: "MG", label: "MG - Minas Gerais" },
  { value: "PA", label: "PA - Pará" },
  { value: "PB", label: "PB - Paraíba" },
  { value: "PR", label: "PR - Paraná" },
  { value: "PE", label: "PE - Pernambuco" },
  { value: "PI", label: "PI - Piauí" },
  { value: "RJ", label: "RJ - Rio de Janeiro" },
  { value: "RN", label: "RN - Rio Grande do Norte" },
  { value: "RS", label: "RS - Rio Grande do Sul" },
  { value: "RO", label: "RO - Rondônia" },
  { value: "RR", label: "RR - Roraima" },
  { value: "SC", label: "SC - Santa Catarina" },
  { value: "SP", label: "SP - São Paulo" },
  { value: "SE", label: "SE - Sergipe" },
  { value: "TO", label: "TO - Tocantins" },
  { value: "ALL", label: "TODAS - Brasil inteiro" },
];

const layerAvailableForUf = (layer: CatalogLayer, uf: string) =>
  uf === "ALL" || !layer.scopeUf || layer.scopeUf === uf;


type AnalysisResult = {
  analysis_id: string;
  area_hectares: number | null;
  results: Array<{
    source_name: string;
    intersects: boolean;
    matched_features: number;
    overlap_hectares: number;
    overlap_percent: number;
    nearest_distance_meters: number | null;
    access_mode: string;
  }>;
  warnings: string[];
  source_statuses?: Array<{
    source_id: string;
    source_name: string;
    institution: string;
    status: "ANALYZED" | "UNAVAILABLE" | "FAILED";
    message: string | null;
    access_mode: string | null;
    source_version_id: string | null;
    reference_date: string | null;
    intersects: boolean | null;
    matched_features: number | null;
    overlap_hectares: number | null;
    overlap_percent: number | null;
    nearest_distance_meters: number | null;
  }>;
  status: "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";
  error_message?: string | null;
};

type SourceHealth = {
  summary: { HEALTHY: number; DOWN: number; NOT_MONITORED: number };
  sources: Array<{ name: string; institution: string; status: string; message: string }>;
};

type AuthUser = {
  id: string;
  email: string;
  full_name: string;
  roles: string[];
  permissions: string[];
};

const fallbackLayers: CatalogLayer[] = [
  {
    name: "Assentamentos INCRA",
    source: "INCRA",
    color: "#ef8354",
    active: true,
  },
  {
    name: "Territórios quilombolas",
    source: "INCRA / Palmares",
    color: "#9b5de5",
    active: true,
  },
  { name: "Terras indígenas", source: "FUNAI", color: "#f6bd60", active: true },
  {
    name: "Unidades de conservação",
    source: "ICMBio / CNUC",
    color: "#36a269",
    active: true,
  },
  {
    name: "Áreas embargadas",
    source: "IBAMA / ICMBio",
    color: "#e63946",
    active: true,
  },
  {
    name: "Sítios arqueológicos",
    source: "IPHAN",
    color: "#2676c9",
    active: false,
  },
  {
    name: "Parcelas fundiárias oficiais",
    source: "INCRA",
    color: "#5b8c5a",
    active: true,
  },
  {
    name: "Parcelas SIGEF mensais",
    source: "Base interna",
    color: "#0d3b66",
    active: true,
  },
];

export default function Home() {
  const [catalog, setCatalog] = useState(fallbackLayers);
  const [enabled, setEnabled] = useState(() =>
    fallbackLayers.map((layer) => layer.active),
  );
  const [apiOnline, setApiOnline] = useState(false);
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [catalogOwnerId, setCatalogOwnerId] = useState<string | null>(null);
  const [subjectGeometry, setSubjectGeometry] = useState<Record<
    string,
    unknown
  > | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisSessionOpen, setAnalysisSessionOpen] = useState(false);
  const [analysisDraftReady, setAnalysisDraftReady] = useState(false);
  const [analysisAreaName, setAnalysisAreaName] = useState("");
  const [analysisHolderName, setAnalysisHolderName] = useState("");
  const [analysisHolderDocument, setAnalysisHolderDocument] = useState("");
  const [analysisResetNonce, setAnalysisResetNonce] = useState(0);
  const [activeView, setActiveView] = useState<
    "map" | "sigef" | "analyses" | "pieces" | "thematic" | "sources" | "users" | "settings"
  >("map");
  const [sigefCurrent, setSigefCurrent] = useState<SourceVersion | null>(null);
  const [pieceRevision, setPieceRevision] = useState(0);
  const [restorePiece, setRestorePiece] = useState<{
    id: string; snapshot: TechnicalPieceSnapshot; nonce: number;
  } | null>(null);
  const [focusRequest, setFocusRequest] = useState<{ sourceId: string; nonce: number } | null>(null);
  const focusSourceOnMap = (sourceId: string) => {
    setFocusRequest((current) => ({ sourceId, nonce: (current?.nonce ?? 0) + 1 }));
  };
  const [layerManagerOpen, setLayerManagerOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [showStatusStrip, setShowStatusStrip] = useState(false);
  const [layerPanelCollapsed, setLayerPanelCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [mobileLayerPanelOpen, setMobileLayerPanelOpen] = useState(false);
  const [incraUf, setIncraUf] = useState("AP");
  const [sourceHealth, setSourceHealth] = useState<SourceHealth | null>(null);
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginLoading, setLoginLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [layerUiTransition, setLayerUiTransition] = useState<{
    layerName: string;
    enabling: boolean;
  } | null>(null);
  const layerUiTimerRef = useRef<number | null>(null);
  const [locationAccess, setLocationAccess] = useState<
    "idle" | "checking" | "allowed" | "denied" | "error"
  >("idle");
  const [locationMessage, setLocationMessage] = useState("");
  const [locationArea, setLocationArea] = useState<string | null>(null);
  const [locationRetryNonce, setLocationRetryNonce] = useState(0);

  const isAnalyst = authUser?.roles.includes("ANALISTA") ?? false;
  const territorialAccessReady =
    Boolean(authUser) && (!isAnalyst || locationAccess === "allowed");

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_URL}/auth/me`, {
      credentials: "include",
    })
      .then(async (response) => {
        if (response.status === 401) return null;
        if (!response.ok) throw new Error("Não foi possível validar a sessão.");
        return response.json();
      })
      .then((user: AuthUser | null) => {
        if (!cancelled) setAuthUser(user);
      })
      .catch(() => {
        if (!cancelled) setAuthUser(null);
      })
      .finally(() => {
        if (!cancelled) setAuthChecking(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!authUser) {
      setLocationAccess("idle");
      setLocationMessage("");
      setLocationArea(null);
      return;
    }

    if (!authUser.roles.includes("ANALISTA")) {
      setLocationAccess("allowed");
      setLocationMessage("");
      setLocationArea(null);
      return;
    }

    if (!("geolocation" in navigator)) {
      setLocationAccess("error");
      setLocationMessage(
        "Este dispositivo ou navegador não disponibiliza geolocalização."
      );
      return;
    }

    let cancelled = false;
    let renewalTimer: number | undefined;

    setLocationAccess("checking");
    setLocationMessage("Obtendo a localização atual do dispositivo…");

    navigator.geolocation.getCurrentPosition(
      async (position) => {
        if (cancelled) return;

        try {
          setLocationMessage("Validando localização autorizada…");

          const response = await fetch(`${API_URL}/auth/location`, {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              latitude: position.coords.latitude,
              longitude: position.coords.longitude,
              accuracy_meters: position.coords.accuracy,
            }),
          });

          const payload = await response.json().catch(() => null);

          if (cancelled) return;

          if (!response.ok) {
            const code = payload?.detail?.code;
            const message =
              payload?.detail?.message ??
              "Não foi possível validar sua localização.";

            if (code === "OUTSIDE_AUTHORIZED_AREA") {
              setLocationAccess("denied");
            } else {
              setLocationAccess("error");
            }

            setLocationMessage(message);
            setLocationArea(null);
            return;
          }

          setLocationAccess("allowed");
          setLocationArea(payload?.area_name ?? null);
          setLocationMessage("Localização autorizada.");

          renewalTimer = window.setTimeout(() => {
            if (!cancelled) {
              setLocationRetryNonce((current) => current + 1);
            }
          }, 12 * 60 * 1000);
        } catch {
          if (!cancelled) {
            setLocationAccess("error");
            setLocationArea(null);
            setLocationMessage(
              "Não foi possível comunicar com o serviço de validação territorial."
            );
          }
        }
      },
      (error) => {
        if (cancelled) return;

        setLocationAccess("error");
        setLocationArea(null);

        if (error.code === error.PERMISSION_DENIED) {
          setLocationMessage(
            "A permissão de localização foi negada. Autorize o acesso ao GPS nas configurações do navegador e tente novamente."
          );
        } else if (error.code === error.POSITION_UNAVAILABLE) {
          setLocationMessage(
            "A localização atual não pôde ser determinada. Verifique o GPS do dispositivo e tente novamente."
          );
        } else {
          setLocationMessage(
            "O tempo para obter a localização foi excedido. Tente novamente."
          );
        }
      },
      {
        enableHighAccuracy: true,
        timeout: 20000,
        maximumAge: 0,
      },
    );

    return () => {
      cancelled = true;
      if (renewalTimer !== undefined) {
        window.clearTimeout(renewalTimer);
      }
    };
  }, [authUser, locationRetryNonce]);

  // Preferências de visualização são isoladas pelo ID do usuário logado.
  // Persistimos apenas identificadores e switches, nunca credenciais.
  useEffect(() => {
    if (!authUser) return;
    try {
      const saved = JSON.parse(localStorage.getItem(`amazonika:layers:${authUser.id}`) ?? "null");
      if (saved?.uf && BRAZIL_STATES.some((state) => state.value === saved.uf)) {
        setIncraUf(saved.uf);
      }
    } catch { /* Preferências locais indisponíveis; usa padrões. */ }
  }, [authUser?.id]);

  useEffect(() => {
    if (!authUser || !catalogLoaded || catalogOwnerId !== authUser.id) return;
    try {
      const flags = Object.fromEntries(catalog.map((layer,index) => [
        String(layer.id ?? layer.slug ?? layer.name), Boolean(enabled[index]),
      ]));
      localStorage.setItem(`amazonika:layers:${authUser.id}`,
        JSON.stringify({ uf: incraUf, flags }));
    } catch { /* Bloqueio de armazenamento não impede funcionamento do mapa. */ }
  }, [authUser?.id, catalogLoaded, catalogOwnerId, catalog, enabled, incraUf]);

  const setLayerEnabled = (index: number, checked: boolean) => {
    const layer = catalog[index];
    if (!layer || layerUiTransition) return;

    setLayerUiTransition({
      layerName: layer.name,
      enabling: checked,
    });

    setEnabled((current) =>
      current.map((value, i) => (i === index ? checked : value)),
    );

    if (layerUiTimerRef.current !== null) {
      window.clearTimeout(layerUiTimerRef.current);
    }

    // Feedback deliberadamente fora do OpenLayers: evita interferir em
    // tileload, zoom, pan ou ciclo de vida do mapa. O bloqueio cobre apenas
    // a troca explícita feita pelo usuário no catálogo.
    layerUiTimerRef.current = window.setTimeout(() => {
      setLayerUiTransition(null);
      layerUiTimerRef.current = null;
    }, 1100);
  };

  useEffect(() => {
    return () => {
      if (layerUiTimerRef.current !== null) {
        window.clearTimeout(layerUiTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!territorialAccessReady) {
      setApiOnline(false);
      return;
    }

    let controller = new AbortController();
    const loadCatalog = () => {
      controller.abort();
      controller = new AbortController();
      fetch(`${API_URL}/sources`, { signal: controller.signal, credentials: "include" })
      .then((response) => {
        if (!response.ok) throw new Error("API indisponível");
        return response.json();
      })
      .then(
        (
          sources: Array<{
            id: string;
            slug: string;
            name: string;
            institution: string;
            is_active: boolean;
            metadata_json?: Record<string, unknown>;
          }>,
        ) => {
          const palette = [
            "#ef8354",
            "#9b5de5",
            "#f6bd60",
            "#36a269",
            "#e63946",
            "#2676c9",
            "#5b8c5a",
            "#0d3b66",
          ];
          if (sources.length) {
            setCatalog(
              sources.map((source, index) => ({
                id: source.id,
                slug: source.slug,
                name: source.name,
                source: source.institution,
                color: palette[index % palette.length],
                active: source.is_active,
                wmsEnabled: Boolean(source.metadata_json?.wms_enabled),
                wmsTheme:
                  typeof source.metadata_json?.wms_theme === "string"
                    ? source.metadata_json.wms_theme
                    : undefined,
                wmsFixedLayer:
                  typeof source.metadata_json?.wms_fixed_layer === "string"
                    ? source.metadata_json.wms_fixed_layer
                    : undefined,
                wmsGlobal: source.metadata_json?.wms_global === true,
                scopeUf:
                  typeof source.metadata_json?.scope_uf === "string"
                    ? source.metadata_json.scope_uf.toUpperCase()
                    : undefined,
                wmsAvailableUfs: Array.isArray(
                  source.metadata_json?.wms_available_ufs,
                )
                  ? source.metadata_json.wms_available_ufs.map((uf) =>
                      String(uf).toUpperCase(),
                    )
                  : undefined,
              })),
            );
            let overrides: Record<string, boolean> = {};
            try {
              const prefs = JSON.parse(localStorage.getItem(`amazonika:layers:${authUser?.id}`) ?? "null");
              if (prefs?.flags && typeof prefs.flags === "object") overrides = prefs.flags;
            } catch { /* usa visibilidade definida pelo catálogo */ }
            setEnabled(sources.map((source) => {
              const key = String(source.id ?? source.slug ?? source.name);
              return typeof overrides[key] === "boolean" ? overrides[key] : source.is_active;
            }));
            setCatalogOwnerId(authUser?.id ?? null);
            setCatalogLoaded(true);
          }
          const sigef = sources.find(
            (source) => source.slug === "sigef-interno",
          );
          if (sigef)
            fetch(`${API_URL}/sources/${sigef.id}/versions`, { credentials: "include" })
              .then((response) => (response.ok ? response.json() : []))
              .then((versions: SourceVersion[]) =>
                setSigefCurrent(
                  versions.find((version) => version.is_current) ?? null,
                ),
              )
              .catch(() => undefined);
          setApiOnline(true);
        },
      )
      .catch((error) => {
        if (error.name !== "AbortError") setApiOnline(false);
      });
    };
    loadCatalog();
    window.addEventListener("amazonika:sources-changed", loadCatalog);
    return () => {
      controller.abort();
      window.removeEventListener("amazonika:sources-changed", loadCatalog);
    };
  }, [authUser, territorialAccessReady]);

  useEffect(() => {
    if (!territorialAccessReady) {
      setSourceHealth(null);
      return;
    }

    let cancelled = false;
    const loadHealth = () => fetch(`${API_URL}/sources/health-status`, { credentials: "include" })
      .then((response) => response.ok ? response.json() : null)
      .then((payload: SourceHealth | null) => { if (!cancelled && payload) setSourceHealth(payload); })
      .catch(() => undefined);
    void loadHealth();
    const interval = window.setInterval(loadHealth, 5 * 60 * 1000);
    return () => { cancelled = true; window.clearInterval(interval); };
  }, [authUser, territorialAccessReady]);

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoginError(null);
    setLoginLoading(true);

    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: loginEmail.trim(),
          password: loginPassword,
        }),
      });

      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          response.status === 401
            ? "E-mail ou senha inválidos."
            : payload?.detail ?? "Não foi possível acessar o sistema.",
        );
      }

      setAuthUser(payload.user);
      setLoginPassword("");
    } catch (error) {
      setLoginError(
        error instanceof Error
          ? error.message
          : "Não foi possível acessar o sistema.",
      );
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API_URL}/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } finally {
      setAuthUser(null);
      setLoginPassword("");
      setLoginError(null);
    }
  };

  const geometryChanged = useCallback(
    (geometry: Record<string, unknown> | null) => {
      setSubjectGeometry(geometry);
      setAnalysis(null);
      setAnalysisError(null);
    },
    [],
  );

  const beginNewAnalysis = () => {
    setActiveView("map");
    setAnalysisSessionOpen(true);
    setAnalysisDraftReady(false);
    setAnalysisAreaName("");
    setAnalysisHolderName("");
    setAnalysisHolderDocument("");
    // A análise é um novo cadastro, não uma ordem para apagar o desenho.
    // Preserva o polígono feito antes de clicar em Nova análise.
    setAnalysis(null);
    setAnalysisError(null);
    setAnalysisProgress("");
  };

  const confirmAnalysisRegistration = () => {
    const areaName = analysisAreaName.trim();
    const holderName = analysisHolderName.trim();
    const digits = analysisHolderDocument.replace(/\D/g, "");

    if (!areaName || !holderName) {
      setAnalysisError("Informe o nome da área/imóvel e o detentor para iniciar a análise.");
      return;
    }

    if (digits && digits.length !== 11 && digits.length !== 14) {
      setAnalysisError("CPF/CNPJ deve possuir 11 ou 14 dígitos.");
      return;
    }

    setAnalysisError(null);
    setAnalysisDraftReady(true);
  };

  const runSpatialAnalysis = async () => {
    if (!subjectGeometry) return;
    if (incraUf === "ALL") {
      setAnalysis(null);
      setAnalysisError(
        "Para executar a análise territorial, selecione uma UF específica. A opção TODAS é destinada à visualização nacional.",
      );
      return;
    }
    setAnalyzing(true);
    setAnalysisError(null);
    setAnalysisProgress("Enviando geometria…");
    try {
        // Somente as fontes ligadas pelo usuário e disponíveis para
        // a UF selecionada participam desta execução territorial.
        const sourceIds = Array.from(
          new Set(
            catalog.flatMap((layer, index) =>
              enabled[index] &&
              layer.id &&
              layerAvailableForUf(layer, incraUf)
                ? [layer.id]
                : [],
            ),
          ),
        );
      const response = await fetch(`${API_URL}/analyses`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: analysisAreaName.trim() || `Consulta ${new Date().toLocaleString("pt-BR")}`,
          geometry: subjectGeometry,
          source_ids: sourceIds,
          incra_uf: incraUf,
          subject: {
            area_name: analysisAreaName.trim(),
            holder_name: analysisHolderName.trim(),
            holder_document: analysisHolderDocument.replace(/\D/g, ""),
          },
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "Não foi possível executar a análise.");
      }
      const accepted = await response.json();
      setAnalysisProgress("Consultando fontes oficiais em segundo plano…");
      let completed: AnalysisResult | null = null;
      for (let attempt = 0; attempt < 240; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const statusResponse = await fetch(
          `${API_URL}/analyses/${accepted.analysis_id}`,
          { credentials: "include" },
        );
        if (!statusResponse.ok)
          throw new Error("Não foi possível acompanhar o processamento.");
        const current = (await statusResponse.json()) as AnalysisResult;
        if (current.status === "FAILED")
          throw new Error(current.error_message || "A análise não pôde ser concluída.");
        if (current.status === "COMPLETED") {
          completed = current;
          break;
        }
        setAnalysisProgress(
          current.status === "PROCESSING"
            ? "Cruzando as camadas oficiais…"
            : "Análise aguardando processamento…",
        );
      }
      if (!completed)
        throw new Error("A análise continua em processamento. Tente consultar novamente em alguns instantes.");
      setAnalysis(completed);
    } catch (error) {
      setAnalysisError(
        error instanceof TypeError
          ? `A API não respondeu em ${API_URL}. Confirme se o container está saudável e tente novamente.`
          : error instanceof Error ? error.message : "Falha inesperada na análise.",
      );
    } finally {
      setAnalyzing(false);
      setAnalysisProgress("");
    }
  };

  if (authChecking) {
    return (
      <main className="auth-loading-screen">
        <div className="auth-loading-spinner" />
        <strong>Amazonika Geoespacial</strong>
        <span>Validando sessão segura…</span>
      </main>
    );
  }

  if (!authUser) {
    return (
      <main className="login-page">
        <div className="login-overlay" />

        <section className="login-brand-panel">
          <p className="login-description login-description-only">
            Plataforma corporativa de inteligência territorial,
            análise espacial e gestão de dados geoespaciais.
          </p>

          <div className="login-coordinate login-coordinate-a">-60.0250</div>
          <div className="login-coordinate login-coordinate-b">-3.4653</div>
        </section>

        <section className="login-form-panel">
          <div className="login-card">
            <div className="login-lock">
              <LockKeyhole size={27} />
            </div>

            <p className="login-eyebrow">ACESSO RESTRITO</p>
            <h1>Acessar sistema</h1>
            <p className="login-subtitle">
              Informe o e-mail e a senha de um usuário autorizado.
            </p>

            <form onSubmit={handleLogin}>
              <label className="login-field">
                <span>E-mail</span>
                <input
                  type="email"
                  autoComplete="username"
                  value={loginEmail}
                  onChange={(event) => setLoginEmail(event.target.value)}
                  placeholder="usuario@amazonikaengenharia.com.br"
                  required
                  autoFocus
                />
              </label>

              <label className="login-field">
                <span>Senha</span>
                <div className="login-password-wrap">
                  <input
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    value={loginPassword}
                    onChange={(event) => setLoginPassword(event.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="login-password-toggle"
                    onClick={() => setShowPassword((current) => !current)}
                    aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                  >
                    {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
                  </button>
                </div>
              </label>

              {loginError && (
                <div className="login-error" role="alert">
                  {loginError}
                </div>
              )}

              <button
                className="login-submit"
                type="submit"
                disabled={loginLoading}
              >
                {loginLoading ? "Autenticando…" : "Entrar no sistema"}
              </button>
            </form>

            <div className="login-security-note">
              <ShieldCheck size={16} />
              <span>Conexão protegida e sessão segura</span>
            </div>
          </div>
        </section>
      </main>
    );
  }

  if (isAnalyst && locationAccess !== "allowed") {
    const denied = locationAccess === "denied";
    const checking = locationAccess === "checking";

    return (
      <main className="location-gate-page">
        <section className="location-gate-card">
          {checking ? (
            <div className="auth-loading-spinner" />
          ) : (
            <div
              className={`location-gate-icon ${
                denied ? "location-gate-icon-denied" : ""
              }`}
            >
              <ShieldCheck size={30} />
            </div>
          )}

          <p className="login-eyebrow">CONTROLE TERRITORIAL</p>

          <h1>
            {checking
              ? "Validando localização"
              : denied
                ? "Área não autorizada"
                : "Localização necessária"}
          </h1>

          <p className="location-gate-message">
            {locationMessage ||
              "Aguarde enquanto verificamos a localização deste dispositivo."}
          </p>

          {!checking && (
            <button
              type="button"
              className="login-submit location-retry-button"
              onClick={() =>
                setLocationRetryNonce((current) => current + 1)
              }
            >
              Tentar novamente
            </button>
          )}

          <button
            type="button"
            className="location-logout-button"
            onClick={handleLogout}
          >
            <LogOut size={16} />
            Sair do sistema
          </button>

          <div className="login-security-note location-security-note">
            <ShieldCheck size={16} />
            <span>
              O acesso operacional é liberado somente dentro das áreas
              autorizadas.
            </span>
          </div>
        </section>
      </main>
    );
  }

  const overlaps =
    analysis?.results.filter((result) => result.intersects) ?? [];
  const largestOverlap = overlaps.reduce(
    (largest, result) => Math.max(largest, result.overlap_percent),
    0,
  );
  return (
    <main className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""} ${mobileSidebarOpen ? "mobile-sidebar-open" : ""}`}>
      <aside className="sidebar">
        <button
          type="button"
          className="sidebar-collapse-button"
          onClick={() => {
            if (window.matchMedia("(max-width: 900px)").matches) {
              setMobileSidebarOpen(false);
            } else {
              setSidebarCollapsed((value) => !value);
            }
          }}
          title={sidebarCollapsed ? "Expandir menu" : "Recolher menu"}
          aria-label={sidebarCollapsed ? "Expandir menu principal" : "Recolher menu principal"}
        >
          {sidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
        <div className="brand">
          <img className="amazonika-brand-logo" src="/amazonika-logo.svg" alt="Logomarca Amazônika Engenharia" />
          <div>
            <strong>AMAZÔNIKA</strong>
            <span>GEOESPACIAL</span>
          </div>
        </div>
        <nav className="main-nav" aria-label="Navegação principal">
          <button
            className={activeView === "map" ? "nav-active" : ""}
            onClick={() => { setActiveView("map"); setMobileSidebarOpen(false); }}
          >
            <Map size={18} /> Visão geográfica
          </button>
          <button
            className={activeView === "sigef" ? "nav-active" : ""}
            onClick={() => { setActiveView("sigef"); setMobileSidebarOpen(false); }}
          >
            <UploadCloud size={18} /> Módulo SIGEF
          </button>
          <button
            className={activeView === "analyses" ? "nav-active" : ""}
            onClick={() => { setActiveView("analyses"); setMobileSidebarOpen(false); }}
          >
            <FileSearch size={18} /> Análises
          </button>
          <button
            className={activeView === "pieces" ? "nav-active" : ""}
            onClick={() => { setActiveView("pieces"); setMobileSidebarOpen(false); }}
          >
            <FileText size={18} /> Peças Técnicas
          </button>
          <button className={activeView === "thematic" ? "nav-active" : ""}
            onClick={() => { setActiveView("thematic"); setMobileSidebarOpen(false); }}>
            <Layers3 size={18}/> Mapas Temáticos
          </button>
          <button
            className={activeView === "sources" ? "nav-active" : ""}
            onClick={() => { setActiveView("sources"); setMobileSidebarOpen(false); }}
          >
            <Database size={18} /> Fontes de dados
          </button>
          {authUser.permissions.includes("users.manage") && (
            <button
              className={activeView === "users" ? "nav-active" : ""}
              onClick={() => { setActiveView("users"); setMobileSidebarOpen(false); }}
            >
              <Users size={18} /> Usuários
            </button>
          )}
        </nav>
        <div className="sidebar-bottom">
          <button
            className={activeView === "settings" ? "nav-active" : ""}
            onClick={() => { setActiveView("settings"); setMobileSidebarOpen(false); }}
          >
            <Settings size={19} /><span className="sr-only">Configurações</span>
          </button>
          <div className="user-card authenticated-user-card">
            <div className="avatar">
              {authUser.full_name
                .split(" ")
                .slice(0, 2)
                .map((part) => part[0])
                .join("")
                .toUpperCase()}
            </div>

            <div className="authenticated-user-info">
              <strong>{authUser.full_name}</strong>
              <span>{authUser.roles.join(", ")}</span>
            </div>

            <button
              type="button"
              className="logout-button"
              onClick={handleLogout}
              title="Sair do sistema"
              aria-label="Sair do sistema"
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      {mobileSidebarOpen && (
        <button
          type="button"
          className="mobile-sidebar-backdrop"
          onClick={() => setMobileSidebarOpen(false)}
          aria-label="Fechar menu principal"
        />
      )}
      <section className="workspace">
        <header className="topbar">
          <button
            type="button"
            className="mobile-main-menu-button"
            onClick={() => setMobileSidebarOpen(true)}
            aria-label="Abrir menu principal"
            title="Menu"
          >
            <Menu size={20} />
          </button>
          <div className="topbar-title">
            <p className="eyebrow">CENTRAL DE ANÁLISE TERRITORIAL</p>
            <h1>
              {activeView === "map"
                ? "Visão geográfica"
                : activeView === "sigef"
                  ? "Gestão SIGEF"
                  : activeView === "analyses"
                    ? "Análises"
                    : activeView === "thematic"
                      ? "Mapas Temáticos"
                    : activeView === "sources"
                      ? "Gestão das fontes"
                      : activeView === "users"
                        ? "Usuários e acessos"
                        : "Configurações"}
            </h1>
          </div>
          {activeView === "map" && (
            <div className="top-actions">
              <button type="button" className="status-toggle" aria-expanded={showStatusStrip}
                onClick={() => setShowStatusStrip(current => !current)}
                title={showStatusStrip ? "Ocultar indicadores" : "Mostrar indicadores"}>
                {showStatusStrip ? <ChevronUp size={17}/> : <ChevronDown size={17}/>}
                {showStatusStrip ? "Ocultar indicadores" : "Mostrar indicadores"}
              </button>
              <Button className="mobile-layers-button" onClick={() => setLayerManagerOpen(true)}>
                <Layers3 size={17} /> Camadas
              </Button>
              <Button className="new-analysis" onClick={beginNewAnalysis}>
                <Plus size={17} /> Nova análise
              </Button>
            </div>
          )}
        </header>
        <div style={{ display: activeView === "map" ? "contents" : "none" }}>
          <>
            {showStatusStrip && <div className="status-strip">
              <div>
                <span
                  className={`status-icon ${apiOnline ? "green" : "amber"}`}
                >
                  <ShieldCheck size={19} />
                </span>
                <p>
                  <strong>
                    {apiOnline
                      ? `${catalog.length} fontes carregadas pela API`
                      : "Interface em modo demonstração"}
                  </strong>
                  <small>
                    {apiOnline
                      ? "Catálogo geoespacial conectado"
                      : "Aguardando a API local"}
                  </small>
                </p>
              </div>
              <div>
                <span className="status-icon blue">
                  <Database size={19} />
                </span>
                <p>
                  <strong>
                    {sigefCurrent?.reference_date
                      ? `SIGEF interno: ${new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" }).format(new Date(`${sigefCurrent.reference_date}T00:00:00Z`))}`
                      : "SIGEF interno: sem carga"}
                  </strong>
                  <small>
                    {sigefCurrent
                      ? `${sigefCurrent.feature_count.toLocaleString("pt-BR")} parcelas na versão ativa`
                      : "Aguardando GeoPackage mensal"}
                  </small>
                </p>
              </div>
              <div>
                <span className={`status-icon ${sourceHealth?.summary.DOWN ? "amber" : "green"}`}>
                  <Activity size={19} />
                </span>
                <p>
                  <strong>{sourceHealth ? sourceHealth.summary.DOWN ? `${sourceHealth.summary.DOWN} fonte${sourceHealth.summary.DOWN === 1 ? "" : "s"} requer${sourceHealth.summary.DOWN === 1 ? "" : "em"} atenção` : "Fontes oficiais respondendo" : "Verificando fontes oficiais…"}</strong>
                  <small title={sourceHealth?.sources.filter((source) => source.status === "DOWN").map((source) => `${source.institution}: ${source.name} — ${source.message}`).join("\n")}>
                    {sourceHealth?.summary.DOWN ? sourceHealth.sources.filter((source) => source.status === "DOWN").slice(0, 2).map((source) => `${source.institution}: ${source.name}`).join(" · ") : sourceHealth ? `${sourceHealth.summary.HEALTHY} serviços monitorados disponíveis` : "Aguarde a primeira verificação"}
                  </small>
                </p>
              </div>
            </div>}
            <div className={`map-layout ${layerPanelCollapsed ? "layer-panel-collapsed" : ""} ${mobileLayerPanelOpen ? "mobile-layer-panel-open" : ""}`}>
              <section className="layer-panel">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">CATÁLOGO</p>
                    <h2>Camadas de análise</h2>
                  </div>
                  <div className="panel-heading-actions">
                    <Badge variant="secondary">
                      {enabled.filter(Boolean).length} ativas
                    </Badge>
                    <button
                      type="button"
                      className="layer-panel-collapse-button"
                      onClick={() => {
                        if (window.matchMedia("(max-width: 900px)").matches) {
                          setMobileLayerPanelOpen(false);
                        } else {
                          setLayerPanelCollapsed(true);
                        }
                      }}
                      aria-label="Recolher painel de camadas"
                      title="Recolher camadas"
                    >
                      <PanelLeftClose size={17} />
                    </button>
                  </div>
                </div>
                <div className="layer-search">
                  <Search size={16} />
                  <input
                    aria-label="Filtrar camadas"
                    placeholder="Filtrar camadas"
                  />
                </div>
                <label className="incra-uf-selector">
                    <span>Estado / UF</span>
                    <select
                      value={incraUf}
                      onChange={(event) => setIncraUf(event.target.value)}
                    >
                      {BRAZIL_STATES.map((state) => (
                        <option key={state.value} value={state.value}>
                          {state.label}
                        </option>
                      ))}
                    </select>
                    <small>
                      Selecione a UF para filtrar as camadas e serviços oficiais.
                    </small>
                </label>
                <div className="layer-list">
                  {catalog.map((layer, index) => (
                    <div className="layer-row" key={layer.name}>
                      <span
                        className="layer-swatch"
                        style={{ background: layer.color }}
                      />
                      <div>
                        <strong>{layer.name}</strong>
                        <small>{layer.source}</small>
                      </div>
                      <button
                        type="button"
                        className="layer-extent-button"
                        disabled={!layer.id || !enabled[index]}
                        onClick={() => layer.id && focusSourceOnMap(layer.id)}
                        title={`Enquadrar feições de ${layer.name}`}
                        aria-label={`Enquadrar camada ${layer.name}`}
                      >
                        <ScanSearch size={16} />
                      </button>
                      <label className="layer-toggle-control">
                        <Switch
                          className="layer-visibility-switch"
                          checked={(enabled[index] ?? false) && layerAvailableForUf(layer, incraUf)}
                          disabled={
                            Boolean(layerUiTransition) ||
                            Boolean(
                              incraUf !== "ALL" &&
                              layer.scopeUf &&
                              layer.scopeUf !== incraUf
                            )
                          }
                          onCheckedChange={(checked) =>
                            setLayerEnabled(index, checked)
                          }
                          aria-label={`Ativar ${layer.name}`}
                        />
                        <span>{incraUf !== "ALL" && layer.scopeUf && layer.scopeUf !== incraUf ? `Somente ${layer.scopeUf}` : enabled[index] ? "Ligada" : "Desligada"}</span>
                      </label>
                    </div>
                  ))}
                </div>
                <button
                  className="manage-layers"
                  onClick={() => setLayerManagerOpen(true)}
                >
                  <Layers3 size={16} /> Gerenciar todas as fontes
                </button>
              </section>
              <section
                className="map-canvas"
                aria-label="Mapa de análise territorial"
              >
                <button
                  type="button"
                  className={`layer-panel-open-button ${layerPanelCollapsed ? "visible" : ""}`}
                  onClick={() => {
                    if (window.matchMedia("(max-width: 900px)").matches) {
                      setMobileLayerPanelOpen(true);
                    } else {
                      setLayerPanelCollapsed(false);
                    }
                  }}
                  aria-label="Abrir painel de camadas"
                  title="Camadas"
                >
                  <Layers3 size={18} />
                  <span>Camadas</span>
                </button>
                {layerUiTransition && (
                  <div
                    className="layer-toggle-feedback"
                    role="status"
                    aria-live="polite"
                    aria-busy="true"
                  >
                    <div className="layer-toggle-feedback-card">
                      <div className="layer-toggle-feedback-spinner" />
                      <div>
                        <strong>
                          {layerUiTransition.enabling
                            ? "Carregando camada…"
                            : "Atualizando camadas…"}
                        </strong>
                        <span>{layerUiTransition.layerName}</span>
                      </div>
                    </div>
                  </div>
                )}
                {mobileLayerPanelOpen && (
                  <button
                    type="button"
                    className="mobile-layer-backdrop"
                    onClick={() => setMobileLayerPanelOpen(false)}
                    aria-label="Fechar painel de camadas"
                  />
                )}
                <GeoMap
                  restorePiece={restorePiece}
                  onPieceSaved={() => setPieceRevision((value) => value + 1)}
                  analysisId={analysis?.status === "COMPLETED" ? analysis.analysis_id : null}
                  incraUf={incraUf}
                  resetNonce={analysisResetNonce}
                  hideAdvancedTools={layerManagerOpen || analysisSessionOpen}
                  analysisPanelOpen={analysisSessionOpen}
                  focusRequest={focusRequest}
                  onGeometryChange={geometryChanged}
                  layers={catalog.map((layer, index) => ({
                    id: layer.id,
                    slug: layer.slug,
                    name: layer.name,
                    color: layer.color,
                    enabled: (enabled[index] ?? false) && layerAvailableForUf(layer, incraUf),
                    featureCount: layer.slug === "sigef-interno" ? (sigefCurrent?.feature_count ?? undefined) : undefined,
                    source: layer.source,
                    wmsEnabled: layer.wmsEnabled,
                    wmsTheme: layer.wmsTheme,
                    wmsFixedLayer: layer.wmsFixedLayer,
                    wmsGlobal: layer.wmsGlobal,
                    wmsAvailableUfs: layer.wmsAvailableUfs,
                  }))}
                />
                {analysisSessionOpen && (
                <div className="analysis-card analysis-card-session">
                  <div className="analysis-title">
                    <span className="status-icon green">
                      <ShieldCheck size={18} />
                    </span>
                    <div>
                      <small>ANÁLISE ESPACIAL</small>
                      <strong>
                        {analysis
                          ? analysis.source_statuses?.some((item) => item.status === "FAILED" || item.status === "UNAVAILABLE")
                            ? "Análise inconclusiva — fonte indisponível"
                            : `${overlaps.reduce((total, item) => total + (item.matched_features ?? 0), 0)} feição(ões) interferente(s) em ${overlaps.length} fonte(s)`
                          : subjectGeometry
                            ? "Geometria pronta para análise"
                            : "Desenhe ou importe uma geometria"}
                      </strong>
                    </div>
                    <button
                      type="button"
                      className="analysis-close-button"
                      onClick={() => setAnalysisSessionOpen(false)}
                      aria-label="Fechar painel de análise espacial"
                      title="Fechar painel sem apagar o desenho"
                    ><X size={17} /></button>
                  </div>
                  {!analysisDraftReady && (
                    <div className="analysis-registration">
                      <label>
                        <span>Área / imóvel</span>
                        <input
                          value={analysisAreaName}
                          onChange={(event) => setAnalysisAreaName(event.target.value)}
                          placeholder="Ex.: Fazenda São José"
                          autoFocus
                        />
                      </label>
                      <label>
                        <span>Detentor</span>
                        <input
                          value={analysisHolderName}
                          onChange={(event) => setAnalysisHolderName(event.target.value)}
                          placeholder="Nome ou razão social"
                        />
                      </label>
                      <label>
                        <span>CPF/CNPJ</span>
                        <input
                          value={analysisHolderDocument}
                          onChange={(event) => setAnalysisHolderDocument(event.target.value)}
                          placeholder="Opcional para análise · necessário para ODS SIGEF"
                          inputMode="numeric"
                        />
                      </label>
                      <Button className="analysis-register-button" onClick={confirmAnalysisRegistration}>
                        Iniciar análise
                      </Button>
                    </div>
                  )}
                  {analysisDraftReady && (
                    <div className="analysis-registration-summary">
                      <strong>{analysisAreaName}</strong>
                      <span>{analysisHolderName}</span>
                    </div>
                  )}
                  {analysisDraftReady && analysis && (
                    <div className="metric-row">
                      <span>
                        Área analisada
                        <strong>
                          {analysis.area_hectares == null
                            ? "Ponto"
                            : `${analysis.area_hectares.toLocaleString("pt-BR", { maximumFractionDigits: 4 })} ha`}
                        </strong>
                      </span>
                      <span>
                        Maior sobreposição
                        <strong>
                          {largestOverlap.toLocaleString("pt-BR", {
                            maximumFractionDigits: 2,
                          })}
                          %
                        </strong>
                      </span>
                    </div>
                  )}
                  {analysisDraftReady && analysis && overlaps.length > 0 && (
                    <div className="overlap-list">
                      {overlaps.slice(0, 3).map((result) => (
                        <span key={result.source_name}>
                          <strong>{result.source_name}</strong>
                          <small>
                            {result.matched_features} feição(ões) ·{" "}
                            {result.overlap_hectares.toLocaleString("pt-BR")} ha
                          </small>
                        </span>
                      ))}
                    </div>
                  )}
                  {analysisDraftReady && analysis && overlaps.length === 0 && !analysis.source_statuses?.some((item) => item.status === "FAILED" || item.status === "UNAVAILABLE") && (
                    <p className="no-overlap">
                      Nenhuma sobreposição identificada nas bases carregadas.
                    </p>
                  )}
                  {analysisError && (
                    <p className="analysis-error">{analysisError}</p>
                  )}
                  {analysisDraftReady && analyzing && analysisProgress && (
                    <p className="analysis-progress">{analysisProgress}</p>
                  )}
                  {analysisDraftReady && analysis?.warnings?.length ? (
                    <p className="analysis-warning">
                      {analysis.warnings.length} fonte(s) não puderam ser consultadas. O relatório registra somente as bases efetivamente analisadas.
                    </p>
                  ) : null}
                  <Button
                    className="report-button"
                    disabled={!analysisDraftReady || !subjectGeometry || analyzing || !apiOnline}
                    onClick={runSpatialAnalysis}
                  >
                    {analyzing
                      ? "Analisando…"
                      : analysis
                        ? "Analisar novamente"
                        : "Executar análise"}
                  </Button>
                  {analysisDraftReady && analysis && (
                    <a
                      className="create-report-button"
                      href={`${API_URL}/reports/analyses/${analysis.analysis_id}/pdf`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <FileText size={17} /> Criar relatório
                    </a>
                  )}
                </div>
                )}
              </section>
            </div>
          </>
        </div>
        {activeView === "sigef" && (
          <SigefModule
            onVersionChanged={(version) => setSigefCurrent(version)}
            onShowOnMap={(sourceId) => {
              focusSourceOnMap(sourceId);
              setActiveView("map");
            }}
          />
        )}
        {activeView === "analyses" && <AnalysesModule />}
        {activeView === "pieces" && (
          <TechnicalPiecesModule revision={pieceRevision}
            onOpen={(piece) => {
              setRestorePiece((previous) => ({
                id: piece.id,
                snapshot: piece.snapshot,
                nonce: (previous?.nonce ?? 0) + 1,
              }));
              setActiveView("map");
            }}
          />
        )}

        {activeView === "thematic" && <ThematicMapsModule />}
        {activeView === "sources" && <SourcesModule />}

        {activeView === "users" &&
          authUser.permissions.includes("users.manage") && (
            <UsersModule />
          )}

        {activeView === "settings" && (
          <>
            <ProfessionalProfile />
            {authUser.permissions.includes("users.manage") && <SettingsModule />}
          </>
        )}
      </section>
      <Sheet open={layerManagerOpen} onOpenChange={setLayerManagerOpen}>
        <SheetContent className="layer-manager-sheet">
          <SheetHeader>
            <SheetTitle>Gerenciar camadas</SheetTitle>
            <SheetDescription>
              Escolha quais fontes aparecem no mapa e participam da
              identificação e da análise.
            </SheetDescription>
          </SheetHeader>
          <div className="layer-manager-actions">
            <button onClick={() => setEnabled(catalog.map(() => true))}>
              Ativar todas
            </button>
            <button onClick={() => setEnabled(catalog.map(() => false))}>
              Desativar todas
            </button>
          </div>
          <div className="layer-manager-summary">
            <Layers3 size={17} />
            <strong>{enabled.filter(Boolean).length}</strong>
            <span>
              de {catalog.length} camadas ativas · UF {incraUf}
            </span>
          </div>
          <div className="layer-manager-list">
            {catalog.map((layer, index) => (
              <div className="layer-manager-row" key={layer.id ?? layer.name}>
                <span
                  className="layer-manager-swatch"
                  style={{ background: layer.color }}
                />
                <div>
                  <strong>{layer.name}</strong>
                  <small>{layer.source}</small>
                </div>
                <label className="layer-toggle-control">
                  <Switch
                    className="layer-visibility-switch"
                    checked={enabled[index] ?? false}
                    onCheckedChange={(checked) =>
                      setLayerEnabled(index, checked)
                    }
                    aria-label={`${enabled[index] ? "Desativar" : "Ativar"} ${layer.name}`}
                  />
                  <span>{enabled[index] ? "Ligada" : "Desligada"}</span>
                </label>
              </div>
            ))}
          </div>
          <p className="layer-manager-note">
            Dica: desligue temporariamente as camadas superiores para
            inspecionar uma fonte isoladamente. Se várias feições continuarem
            sob o clique, o identificador mostrará uma lista para escolha.
          </p>
        </SheetContent>
      </Sheet>
    </main>
  );
}
