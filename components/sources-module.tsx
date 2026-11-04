"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { getApiUrl } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  CheckCircle2,
  Database,
  ExternalLink,
  FileUp,
  Globe2,
  RefreshCw,
  Server,
  Settings,
  TriangleAlert,
} from "lucide-react";

const API_URL = getApiUrl();
const INCRA_PORTAL_URL =
  "https://acervofundiario.incra.gov.br/i3geo/geodownload/geodados.php";
type Source = {
  id: string;
  slug: string;
  name: string;
  institution: string;
  kind: string;
  service_url: string | null;
  layer_name: string | null;
  is_official: boolean;
  is_active: boolean;
  update_frequency: string | null;
  metadata_json: Record<string, unknown>;
};
type SourceVersion = {
  id: string;
  source_id: string;
  reference_date: string | null;
  imported_at: string | null;
  feature_count: number;
  status: string;
  is_current: boolean;
  error_message: string | null;
};

function formatDate(value: string | null | undefined) {
  return value
    ? new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(new Date(value))
    : "Ainda não sincronizada";
}
function formatFrequency(value: string | null) {
  return (
    (
      {
        DIARIA: "Diária",
        SEMANAL: "Semanal",
        QUINZENAL: "Quinzenal",
        MENSAL: "Mensal",
        CONFORME_FONTE: "Conforme a fonte",
      } as Record<string, string>
    )[value ?? ""] ??
    value ??
    "Não definida"
  );
}
function versionAge(version: SourceVersion | null | undefined) {
  if (!version?.reference_date) return null;
  return Math.max(
    0,
    Math.floor(
      (Date.now() - new Date(`${version.reference_date}T00:00:00Z`).getTime()) /
        86400000,
    ),
  );
}

function SourceSettingsDialog({
  source,
  onClose,
  onChanged,
}: {
  source: Source | null;
  onClose: () => void;
  onChanged: (text: string) => Promise<void>;
}) {
  const [kind, setKind] = useState("WFS"),
    [serviceUrl, setServiceUrl] = useState(""),
    [layerName, setLayerName] = useState(""),
    [frequency, setFrequency] = useState("MENSAL");
  const [wmsUrl, setWmsUrl] = useState(""),
    [wmsLayer, setWmsLayer] = useState(""),
    [wmsEnabled, setWmsEnabled] = useState(false),
    [wmsGlobal, setWmsGlobal] = useState(false),
    [allowLegacy, setAllowLegacy] = useState(false);
  const [file, setFile] = useState<File | null>(null),
    [referenceDate, setReferenceDate] = useState(
      new Date().toISOString().slice(0, 10),
    ),
    [manualLayer, setManualLayer] = useState("");
  const [saving, setSaving] = useState(false),
    [uploading, setUploading] = useState(false),
      [uploadProgress, setUploadProgress] = useState(0),
      [uploadPhase, setUploadPhase] = useState(""),
    [testingWms, setTestingWms] = useState(false),
    [wmsTest, setWmsTest] = useState<"success" | "error" | null>(null),
    [error, setError] = useState<string | null>(null);
  const institution = source?.institution.toUpperCase() ?? "";
  const isIncra = institution === "INCRA";
  const isSicar = institution === "SICAR";
  const isSpu = institution === "SPU";
  const isWmsReference = isIncra || isSicar || isSpu;
  useEffect(() => {
    if (!source) return;
    setKind(source.kind);
    setServiceUrl(source.service_url ?? "");
    setLayerName(source.layer_name ?? "");
    setFrequency(source.update_frequency ?? "MENSAL");
    setWmsUrl(String(source.metadata_json.wms_url ?? ""));
    setWmsLayer(String(source.metadata_json.wms_fixed_layer ?? source.metadata_json.wms_layer ?? ""));
    setWmsGlobal(Boolean(source.metadata_json.wms_global));
    setWmsEnabled(Boolean(source.metadata_json.wms_enabled));
    setAllowLegacy(
      isIncra && Boolean(source.metadata_json.allow_insecure_tls),
    );
    setFile(null);
    setManualLayer("");
    setUploadProgress(0);
    setUploadPhase("");
    setWmsTest(null);
    setError(null);
  }, [source]);
  const testWms = async () => {
    if (!source) return;
    setTestingWms(true);
    setWmsTest(null);
    setError(null);
    try {
      // The proxy uses persisted source settings; testing unsaved edits would
      // silently probe the previous URL/layer and produce misleading results.
      if (
        wmsUrl.trim() !== String(source.metadata_json.wms_url ?? "").trim() ||
        wmsLayer.trim() !== String(source.metadata_json.wms_fixed_layer ?? source.metadata_json.wms_layer ?? "").trim() ||
        (isIncra && wmsGlobal !== Boolean(source.metadata_json.wms_global))
      ) {
        throw new Error("Salve a configuração antes de testar o novo endereço e a camada WMS.");
      }
      const params = new URLSearchParams({
        uf: "ap",
        service: "WMS",
        request: "GetCapabilities",
        version: "1.1.1",
      });
      const response = await fetch(
        `${API_URL}/sources/${source.id}/wms?${params}`,
        { credentials: "include" },
      );
      const body = await response.text();
      if (!response.ok) {
        let detail = "O proxy WMS não respondeu (HTTP " + response.status + ").";
        const contentType = response.headers.get("content-type") ?? "";
        if (contentType.includes("application/json")) {
          try {
            const parsed = JSON.parse(body);
            if (typeof parsed?.detail === "string") detail = parsed.detail.slice(0, 250);
          } catch { /* mantém mensagem segura */ }
        }
        if (response.status === 502) {
          detail = "Falha na conexão com o WMS (HTTP 502). Verifique a API e o serviço oficial.";
        }
        throw new Error(detail);
      }
      const expected = String(
        source.metadata_json.wms_fixed_layer || source.metadata_json.wms_theme || wmsLayer,
      ).toLowerCase();
      if (
        !/WMT_MS_Capabilities|WMS_Capabilities/i.test(body) ||
        (expected && !body.toLowerCase().includes(expected))
      ) {
        throw new Error(
          "O endereço respondeu, mas não confirmou a camada configurada.",
        );
      }
      setWmsTest("success");
    } catch (reason) {
      setWmsTest("error");
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao testar o WMS oficial.",
      );
    } finally {
      setTestingWms(false);
    }
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!source) return;
    setSaving(true);
    setError(null);
    try {
      const payload = isWmsReference
        ? {
            kind: "DOWNLOAD",
            service_url: null,
            layer_name: null,
            update_frequency: frequency,
            wms_url: wmsUrl || null,
            wms_layer: wmsLayer || null,
            wms_fixed_layer: wmsLayer || null,
            wms_global: isIncra ? wmsGlobal : false,
            wms_enabled: wmsEnabled,
            allow_insecure_tls: isIncra ? allowLegacy : false,
            stale_after_days: 15,
            requires_auth: false,
            access_mode: "PUBLIC_WMS",
            service_role: isIncra
              ? "WMS_REFERENCE_WITH_VECTOR_SNAPSHOT"
              : "WMS_REFERENCE",
          }
        : {
            kind,
            service_url: serviceUrl || null,
            layer_name: layerName || null,
            update_frequency: frequency,
            stale_after_days: 15,
          };
      const response = await fetch(`${API_URL}/sources/${source.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok)
        throw new Error(
          body?.detail ?? "Não foi possível salvar a configuração.",
        );
      await onChanged(`Configuração de ${source.name} atualizada.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar.");
    } finally {
      setSaving(false);
    }
  };
  const upload = async (event: FormEvent) => {
    event.preventDefault();
    if (!source || !file) return;

    const LARGE_UPLOAD_THRESHOLD = 80 * 1024 * 1024;
    const CHUNK_SIZE = 25 * 1024 * 1024;
    const resumeKey = `amazonika-large-upload:${source.id}:${file.name}:${file.size}`;

    setUploading(true);
    setUploadProgress(0);
    setUploadPhase("");
    setError(null);

    try {
      if (file.size <= LARGE_UPLOAD_THRESHOLD) {
        setUploadPhase("Importando arquivo…");

        const data = new FormData();
        data.append("file", file);
        data.append("reference_date", referenceDate);
        if (manualLayer.trim()) data.append("layer_name", manualLayer.trim());

        const response = await fetch(
          `${API_URL}/sources/${source.id}/imports/vector`,
          { method: "POST", body: data },
        );

        const body = await response.json().catch(() => null);

        if (!response.ok)
          throw new Error(
            body?.detail ?? "Não foi possível importar o vetor.",
          );

        setUploadProgress(100);

        await onChanged(
          `${source.name}: ${Number(body.feature_count).toLocaleString("pt-BR")} feições importadas e ativadas.`,
        );

        setFile(null);
        return;
      }

      setUploadPhase("Preparando upload grande…");

      let uploadId = "";
      let offset = 0;

      const previous = window.localStorage.getItem(resumeKey);

      if (previous) {
        try {
          const saved = JSON.parse(previous);

          if (saved?.upload_id) {
            const statusResponse = await fetch(
              `${API_URL}/sources/${source.id}/uploads/${saved.upload_id}/status`,
            );

            if (statusResponse.ok) {
              const status = await statusResponse.json();

              if (
                Number(status.file_size) === file.size &&
                status.filename === file.name &&
                status.status === "UPLOADING"
              ) {
                uploadId = saved.upload_id;
                offset = Number(status.received_bytes) || 0;
              } else {
                window.localStorage.removeItem(resumeKey);
              }
            } else {
              window.localStorage.removeItem(resumeKey);
            }
          }
        } catch {
          window.localStorage.removeItem(resumeKey);
        }
      }

      if (!uploadId) {
        const startResponse = await fetch(
          `${API_URL}/sources/${source.id}/uploads/start`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              filename: file.name,
              file_size: file.size,
              reference_date: referenceDate,
              layer_name: manualLayer.trim() || null,
            }),
          },
        );

        const started = await startResponse.json().catch(() => null);

        if (!startResponse.ok)
          throw new Error(
            started?.detail ?? "Não foi possível iniciar o upload.",
          );

        uploadId = started.upload_id;
        offset = Number(started.received_bytes) || 0;

        window.localStorage.setItem(
          resumeKey,
          JSON.stringify({ upload_id: uploadId }),
        );
      }

      setUploadPhase(
        offset > 0 ? "Retomando upload…" : "Enviando arquivo…",
      );

      while (offset < file.size) {
        const endOffset = Math.min(offset + CHUNK_SIZE, file.size);
        const blob = file.slice(offset, endOffset);

        const data = new FormData();
        data.append("offset", String(offset));
        data.append("chunk", blob, `${file.name}.part`);

        const chunkResponse = await fetch(
          `${API_URL}/sources/${source.id}/uploads/${uploadId}/chunk`,
          { method: "POST", body: data },
        );

        const chunkBody = await chunkResponse.json().catch(() => null);

        if (!chunkResponse.ok) {
          if (chunkResponse.status === 409) {
            const statusResponse = await fetch(
              `${API_URL}/sources/${source.id}/uploads/${uploadId}/status`,
            );

            if (statusResponse.ok) {
              const status = await statusResponse.json();
              offset = Number(status.received_bytes) || offset;
              setUploadProgress(
                Math.min(99, Math.round((offset / file.size) * 100)),
              );
              continue;
            }
          }

          throw new Error(
            chunkBody?.detail ??
              "Falha durante o envio de uma parte do arquivo.",
          );
        }

        offset = Number(chunkBody.received_bytes);

        setUploadProgress(
          Math.min(99, Math.round((offset / file.size) * 100)),
        );
      }

      setUploadPhase("Finalizando arquivo…");

      const completeResponse = await fetch(
        `${API_URL}/sources/${source.id}/uploads/${uploadId}/complete`,
        { method: "POST" },
      );

      const completed = await completeResponse.json().catch(() => null);

      if (!completeResponse.ok)
        throw new Error(
          completed?.detail ?? "Não foi possível finalizar o upload.",
        );

      window.localStorage.removeItem(resumeKey);

      setUploadProgress(100);
      setUploadPhase("Arquivo recebido pelo servidor.");

      await onChanged(
        `${source.name}: arquivo ${file.name} recebido integralmente. Aguardando processamento da base vetorial.`,
      );

      setFile(null);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Falha durante o upload.",
      );
    } finally {
      setUploading(false);
    }
  };

  return (
    <Dialog
      open={Boolean(source)}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="source-settings-dialog">
        <DialogHeader>
          <DialogTitle>Configurar {source?.name}</DialogTitle>
          <DialogDescription>
            Visualização oficial e cópia vetorial analisável são controladas
            separadamente.
          </DialogDescription>
        </DialogHeader>
        {error && (
          <div className="source-dialog-error">
            <TriangleAlert size={16} />
            {error}
          </div>
        )}
        <form className="source-config-form" onSubmit={save}>
          <div className="source-dialog-section-title">
            <Globe2 size={17} />
            <div>
              <strong>
                {isWmsReference
                  ? "Visualização oficial WMS"
                  : "Conexão automática vetorial"}
              </strong>
              <small>
                {isWmsReference
                  ? "Serviço oficial usado somente como referência visual"
                  : "WFS ou ArcGIS FeatureServer"}
              </small>
            </div>
          </div>
          {isWmsReference ? (
            <>
              <div className="source-config-grid">
                <label className="wide">
                  <span>Endereço WMS oficial</span>
                  <input
                    type="url"
                    value={wmsUrl}
                    onChange={(event) => setWmsUrl(event.target.value)}
                  />
                </label>
                <label className="wide">
                  <span>Camada atual</span>
                  <input
                    value={wmsLayer}
                    onChange={(event) => setWmsLayer(event.target.value)}
                  />
                </label>
                <label>
                  <span>Frequência da cópia vetorial</span>
                  <select
                    value={frequency}
                    onChange={(event) => setFrequency(event.target.value)}
                  >
                    <option value="QUINZENAL">Quinzenal</option>
                    <option value="MENSAL">Mensal</option>
                  </select>
                </label>
                <div className="source-switch-field">
                  <span>Exibir WMS no mapa</span>
                  <Switch
                    className="source-config-switch"
                    checked={wmsEnabled}
                    onCheckedChange={setWmsEnabled}
                  />
                </div>
                {isIncra && <div className="source-switch-field wide">
                  <span>Camada nacional (sem sufixo por UF, como no GeoNode SIGEF)</span>
                  <Switch className="source-config-switch" checked={wmsGlobal}
                    onCheckedChange={setWmsGlobal}/>
                </div>}
                {isIncra && (
                  <div className="source-switch-field wide">
                    <span>
                      Permitir conexão legada somente com o domínio oficial do
                      INCRA
                    </span>
                    <Switch
                      className="source-config-switch"
                      checked={allowLegacy}
                      onCheckedChange={setAllowLegacy}
                    />
                  </div>
                )}
              </div>
              <div className="wms-reference-warning">
                <Globe2 size={16} />
                <span>
                  {isIncra ? (
                    <>
                      O gov.br serve apenas para consultar/copiar URLs. O WMS
                      funciona sem login. A exceção legada fica restrita a{" "}
                      <strong>acervofundiario.incra.gov.br</strong>.
                    </>
                  ) : (
                    <>
                      O WMS é somente referência visual e pode permanecer
                      desligado. Identificação, análise e relatório utilizam
                      os vetores carregados no PostGIS pelo módulo{" "}
                      <strong>Vetores adicionais por UF</strong>.
                    </>
                  )}
                </span>
              </div>
              <button
                className={`wms-test-button ${wmsTest ?? ""}`}
                type="button"
                onClick={() => void testWms()}
                disabled={testingWms || !wmsEnabled}
              >
                {testingWms ? (
                  <>
                    <RefreshCw size={14} className="spin" /> Testando conexão
                    oficial…
                  </>
                ) : wmsTest === "success" ? (
                  <>
                    <CheckCircle2 size={14} /> WMS oficial conectado
                  </>
                ) : (
                  <>
                    <Server size={14} /> Testar conexão WMS oficial
                  </>
                )}
              </button>
            </>
          ) : (
            <div className="source-config-grid">
              <label>
                <span>Tipo</span>
                <select
                  value={kind}
                  onChange={(event) => setKind(event.target.value)}
                >
                  <option value="WFS">WFS</option>
                  <option value="ARCGIS_FEATURE">ArcGIS FeatureServer</option>
                  <option value="MANUAL">Somente manual</option>
                </select>
              </label>
              <label>
                <span>Frequência</span>
                <select
                  value={frequency}
                  onChange={(event) => setFrequency(event.target.value)}
                >
                  <option value="DIARIA">Diária</option>
                  <option value="SEMANAL">Semanal</option>
                  <option value="QUINZENAL">Quinzenal</option>
                  <option value="MENSAL">Mensal</option>
                </select>
              </label>
              <label className="wide">
                <span>Endereço vetorial</span>
                <input
                  type="url"
                  value={serviceUrl}
                  onChange={(event) => setServiceUrl(event.target.value)}
                />
              </label>
              <label className="wide">
                <span>Camada / identificador</span>
                <input
                  value={layerName}
                  onChange={(event) => setLayerName(event.target.value)}
                />
              </label>
            </div>
          )}
          <div className="source-config-actions">
            {isIncra ? (
              <a href={INCRA_PORTAL_URL} target="_blank" rel="noreferrer">
                <ExternalLink size={14} /> Consultar URLs no INCRA
              </a>
            ) : (
              <span />
            )}
            <Button disabled={saving}>
              {saving ? (
                <>
                  <RefreshCw size={15} className="spin" /> Salvando…
                </>
              ) : (
                "Salvar configuração"
              )}
            </Button>
          </div>
        </form>
        {isWmsReference || ["ASSENTAMENTOS", "SIGEF", "SNCI"].includes(
          String(source?.metadata_json.source_group ?? ""),
        ) ? (
          <div className="source-package-managed-note">
            <Database size={17} />
            <div>
              <strong>
                {isWmsReference
                  ? "Vetor operacional separado do WMS"
                  : "Atualização controlada por pacote"}
              </strong>
              <small>
                {isWmsReference
                  ? "Use Vetores adicionais por UF para carregar a base PostGIS usada no mapa, Identificar, análise e relatório."
                  : "Esta fonte faz parte de um GeoPackage composto. Use o botão de atualização no cabeçalho do grupo para manter todas as camadas sincronizadas."}
              </small>
            </div>
          </div>
        ) : (
        <form className="source-manual-form" onSubmit={upload}>
          <div className="source-dialog-section-title">
            <FileUp size={17} />
            <div>
              <strong>Base vetorial para análise e relatório</strong>
              <small>
                GeoPackage, KML, GeoJSON ou Shapefile ZIP · alerta após 15 dias
              </small>
            </div>
          </div>
          <label className="source-vector-drop">
            <FileUp size={22} />
            <strong>{file ? file.name : "Selecionar arquivo vetorial"}</strong>
            <small>
              {file
                ? `${(file.size / 1024 / 1024).toFixed(2)} MB`
                : ".gpkg, .kml, .geojson, .json ou .zip"}
            </small>
            <input
              type="file"
              accept=".gpkg,.kml,.geojson,.json,.zip"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <div className="source-config-grid compact">
            <label>
              <span>Data de referência</span>
              <input
                type="date"
                required
                value={referenceDate}
                onChange={(event) => setReferenceDate(event.target.value)}
              />
            </label>
            <label>
              <span>Camada interna (opcional)</span>
              <input
                placeholder="ZIP ou GeoPackage com várias camadas"
                value={manualLayer}
                onChange={(event) => setManualLayer(event.target.value)}
              />
            </label>
          </div>
          {uploading && uploadPhase && (
            <div style={{ display: "grid", gap: 6 }}>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: 12,
                }}
              >
                <span>{uploadPhase}</span>
                <strong>{uploadProgress}%</strong>
              </div>
              <progress
                value={uploadProgress}
                max={100}
                style={{ width: "100%", height: 10 }}
              />
            </div>
          )}
          <Button
            className="source-upload-button"
            disabled={!file || uploading}
          >
            {uploading ? (
              <>
                <RefreshCw size={15} className="spin" />{" "}
                {file && file.size > 80 * 1024 * 1024
                  ? `Enviando ${uploadProgress}%`
                  : "Importando…"}
              </>
            ) : (
              <>
                <FileUp size={15} /> Importar e ativar versão
              </>
            )}
          </Button>
        </form>
        )}
      </DialogContent>
    </Dialog>
  );
}


type SourcePackageGroup = {
  key: string;
  label: string;
  sources: Source[];
};

type PackageInspection = {
  valid?: boolean;
  expected_package?: string;
  received_package?: string;
  available_layers?: string[];
  missing_layers?: string[];
  mappings?: Array<{
    source_id: string;
    source_name: string;
    expected_layer: string;
    actual_layer: string;
  }>;
};

type PackageLayerResult = {
  source_id: string;
  source_name: string;
  layer_name: string;
  version_id: string;
  feature_count: number;
};

type PackageUploadState = {
  upload_id?: string;
  status?: string;
  group?: string;
  filename?: string;
  file_size?: number;
  received_bytes?: number;

  processing_stage?: string | null;
  processing_code?: string | null;
  progress_percent?: number;

  processing_started_at?: string | null;
  processing_finished_at?: string | null;

  current_layer?: string | null;
  current_source?: string | null;
  current_layer_index?: number | null;
  total_layers?: number | null;
  current_layer_total_features?: number | null;
  completed_layers?: PackageLayerResult[];

  error?: string | null;
  error_code?: string | null;
  error_title?: string | null;
  error_detail?: string | null;
  error_retryable?: boolean;

  file_removed_after_processing?: boolean;
  cleanup_warning?: string | null;

  inspection?: PackageInspection;

  result?: {
    results?: PackageLayerResult[];
  };
};

function PackageUploadDialog({
  group,
  onClose,
  onCompleted,
}: {
  group: SourcePackageGroup | null;
  onClose: () => void;
  onCompleted: (text: string) => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [referenceDate, setReferenceDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState("");
  const [session, setSession] = useState<PackageUploadState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const expectedPackage = useMemo(() => {
    if (!group) return "";
    const names = new Set(
      group.sources
        .map((source) =>
          String(source.metadata_json.source_package ?? "").trim(),
        )
        .filter(Boolean),
    );
    return names.size === 1 ? Array.from(names)[0] : "";
  }, [group]);

  useEffect(() => {
    if (!group) return;
    setFile(null);
    setUploading(false);
    setProcessing(false);
    setProgress(0);
    setPhase("");
    setSession(null);
    setError(null);
    setReferenceDate(new Date().toISOString().slice(0, 10));
  }, [group?.key]);

  const pollProcessing = async (uploadId: string) => {
    setProcessing(true);

    try {
      for (;;) {
        const response = await fetch(
          `${API_URL}/sources/packages/uploads/${uploadId}/status`,
        );
        const body: PackageUploadState = await response.json();

        if (!response.ok) {
          throw new Error(
            (body as { detail?: string }).detail ??
              "Não foi possível consultar o processamento.",
          );
        }

        setSession(body);
        setPhase(body.processing_stage ?? "Processando pacote…");
        setProgress(
          Math.max(
            0,
            Math.min(100, Number(body.progress_percent ?? 0)),
          ),
        );

        if (body.status === "READY") {
          setProgress(100);
          setProcessing(false);

          const results = body.result?.results ?? [];
          const total = results.reduce(
            (sum, item) => sum + Number(item.feature_count || 0),
            0,
          );

          await onCompleted(
            `${group?.label ?? "Pacote"}: ${results.length} camadas atualizadas, ${total.toLocaleString("pt-BR")} feições processadas.`,
          );

          return;
        }

        if (body.status === "FAILED") {
          throw new Error(body.error || "O processamento do pacote falhou.");
        }

        await new Promise((resolve) => window.setTimeout(resolve, 3000));
      }
    } catch (reason) {
      setProcessing(false);
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao acompanhar o processamento.",
      );
    }
  };

  useEffect(() => {
    if (!group?.key) return;

    let cancelled = false;

    const recoverPackageJob = async () => {
      try {
        const response = await fetch(
          `${API_URL}/sources/packages/jobs/current?group=${encodeURIComponent(group.key)}`,
        );

        if (!response.ok) return;

        const body = await response.json();
        const job: PackageUploadState | null = body?.job ?? null;

        if (cancelled || !job?.upload_id) return;

        setSession(job);

        if (job.status === "UPLOADING") {
          const total = Number(job.file_size || 0);
          const received = Number(job.received_bytes || 0);

          const recoveredProgress =
            total > 0
              ? Math.min(
                  99,
                  Math.round((received / total) * 100),
                )
              : 0;

          setProgress(recoveredProgress);
          setPhase(
            `Upload interrompido em ${recoveredProgress}%. Selecione novamente o mesmo arquivo para continuar.`,
          );
          setProcessing(false);
          return;
        }

        if (job.status === "UPLOADED") {
          setPhase("Validando camadas internas…");

          const inspectResponse = await fetch(
            `${API_URL}/sources/packages/uploads/${job.upload_id}/inspect`,
            {
              method: "POST",
            },
          );

          const inspected = await inspectResponse.json().catch(() => null);

          if (!inspectResponse.ok) {
            throw new Error(
              inspected?.detail ??
                "Não foi possível validar o GeoPackage armazenado.",
            );
          }

          if (cancelled) return;

          setSession(inspected);
          setPhase(
            inspected?.inspection?.valid
              ? "Pacote validado. Pronto para processar."
              : "GeoPackage incompleto.",
          );
          setProcessing(false);
          return;
        }

        setPhase(job.processing_stage ?? "");
        setProgress(
          Math.max(
            0,
            Math.min(100, Number(job.progress_percent ?? 0)),
          ),
        );

        if (
          job.status === "QUEUED" ||
          job.status === "PROCESSING"
        ) {
          void pollProcessing(job.upload_id);
          return;
        }

        setProcessing(false);
      } catch {
        // Recuperação automática é auxiliar.
      }
    };

    void recoverPackageJob();

    return () => {
      cancelled = true;
    };
  }, [group?.key]);

  const uploadPackage = async () => {
    if (!group || !file) return;

    if (expectedPackage && file.name !== expectedPackage) {
      setError(
        `Arquivo incorreto. Para este grupo selecione exatamente ${expectedPackage}.`,
      );
      return;
    }

    const CHUNK_SIZE = 25 * 1024 * 1024;
    const resumeKey = `amazonika-package-upload:${group.key}:${file.name}:${file.size}`;

    setUploading(true);
    setError(null);
    setProgress(0);
    setPhase("Preparando pacote…");

    try {
      let uploadId = "";
      let offset = 0;

      if (
        session?.status === "UPLOADING" &&
        session.upload_id &&
        session.filename === file.name &&
        Number(session.file_size) === file.size &&
        session.group === group.key
      ) {
        uploadId = session.upload_id;
        offset = Number(session.received_bytes || 0);

        window.localStorage.setItem(
          resumeKey,
          JSON.stringify({ upload_id: uploadId }),
        );
      }

      const previous = window.localStorage.getItem(resumeKey);

      if (!uploadId && previous) {
        try {
          const saved = JSON.parse(previous);

          if (saved?.upload_id) {
            const statusResponse = await fetch(
              `${API_URL}/sources/packages/uploads/${saved.upload_id}/status`,
            );

            if (statusResponse.ok) {
              const status: PackageUploadState = await statusResponse.json();

              if (
                Number(status.file_size) === file.size &&
                status.filename === file.name &&
                status.group === group.key &&
                status.status === "UPLOADING"
              ) {
                uploadId = saved.upload_id;
                offset = Number(status.received_bytes || 0);
              } else {
                window.localStorage.removeItem(resumeKey);
              }
            } else {
              window.localStorage.removeItem(resumeKey);
            }
          }
        } catch {
          window.localStorage.removeItem(resumeKey);
        }
      }

      if (!uploadId) {
        const startResponse = await fetch(
          `${API_URL}/sources/packages/uploads/start`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              group: group.key,
              filename: file.name,
              file_size: file.size,
              reference_date: referenceDate,
            }),
          },
        );

        const started = await startResponse.json().catch(() => null);

        if (!startResponse.ok) {
          throw new Error(
            started?.detail ?? "Não foi possível iniciar o upload do pacote.",
          );
        }

        uploadId = started.upload_id;
        offset = Number(started.received_bytes || 0);
        setSession(started);

        window.localStorage.setItem(
          resumeKey,
          JSON.stringify({ upload_id: uploadId }),
        );
      }

      setPhase(offset > 0 ? "Retomando upload…" : "Enviando GeoPackage…");

      while (offset < file.size) {
        const endOffset = Math.min(offset + CHUNK_SIZE, file.size);
        const blob = file.slice(offset, endOffset);
        const data = new FormData();

        data.append("offset", String(offset));
        data.append("chunk", blob, `${file.name}.part`);

        const chunkResponse = await fetch(
          `${API_URL}/sources/packages/uploads/${uploadId}/chunk`,
          {
            method: "POST",
            body: data,
          },
        );

        const chunkBody = await chunkResponse.json().catch(() => null);

        if (!chunkResponse.ok) {
          if (chunkResponse.status === 409) {
            const statusResponse = await fetch(
              `${API_URL}/sources/packages/uploads/${uploadId}/status`,
            );

            if (statusResponse.ok) {
              const status: PackageUploadState =
                await statusResponse.json();

              offset = Number(status.received_bytes || offset);

              setProgress(
                Math.min(
                  99,
                  Math.round((offset / file.size) * 100),
                ),
              );

              continue;
            }
          }

          throw new Error(
            chunkBody?.detail ?? "Falha durante o envio do pacote.",
          );
        }

        offset = Number(chunkBody.received_bytes || 0);

        setProgress(
          Math.min(
            99,
            Math.round((offset / file.size) * 100),
          ),
        );
      }

      setPhase("Finalizando upload…");

      const completeResponse = await fetch(
        `${API_URL}/sources/packages/uploads/${uploadId}/complete`,
        {
          method: "POST",
        },
      );

      const completed = await completeResponse.json().catch(() => null);

      if (!completeResponse.ok) {
        throw new Error(
          completed?.detail ?? "Não foi possível finalizar o pacote.",
        );
      }

      window.localStorage.removeItem(resumeKey);

      setProgress(100);
      setSession(completed);
      setPhase("Validando camadas internas…");

      const inspectResponse = await fetch(
        `${API_URL}/sources/packages/uploads/${uploadId}/inspect`,
        {
          method: "POST",
        },
      );

      const inspected = await inspectResponse.json().catch(() => null);

      if (!inspectResponse.ok) {
        throw new Error(
          inspected?.detail ?? "Não foi possível validar o GeoPackage.",
        );
      }

      setSession(inspected);

      if (!inspected?.inspection?.valid) {
        const missing =
          inspected?.inspection?.missing_layers?.join(", ") || "não informadas";

        throw new Error(
          `Pacote inválido. Camadas ausentes: ${missing}.`,
        );
      }

      setPhase("Pacote validado. Pronto para processar.");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha durante o upload do pacote.",
      );
    } finally {
      setUploading(false);
    }
  };

  const processPackage = async () => {
    if (!session?.upload_id) return;

    setError(null);
    setProcessing(true);
    setPhase("Enviando pacote para processamento…");

    try {
      const response = await fetch(
        `${API_URL}/sources/packages/uploads/${session.upload_id}/process`,
        {
          method: "POST",
        },
      );

      const body = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          body?.detail ?? "Não foi possível iniciar o processamento.",
        );
      }

      setSession((current) => ({
        ...(current ?? {}),
        ...body,
      }));

      await pollProcessing(session.upload_id);
    } catch (reason) {
      setProcessing(false);
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao iniciar o processamento.",
      );
    }
  };

  const inspection = session?.inspection;
  const mappings = inspection?.mappings ?? [];

  const jobStatus = session?.status ?? "";

  const jobProgress = Math.max(
    0,
    Math.min(
      100,
      Number(
        session?.progress_percent ??
          (uploading ? progress : 0),
      ),
    ),
  );

  const completedLayers = session?.completed_layers ?? [];

  const completedSourceIds = new Set(
    completedLayers.map((item) => item.source_id),
  );

  const showJobProgress = [
    "QUEUED",
    "PROCESSING",
    "READY",
    "FAILED",
  ].includes(jobStatus);

  const retryAvailable =
    jobStatus === "FAILED" &&
    Boolean(session?.error_retryable) &&
    Boolean(session?.upload_id);

  return (
    <Dialog
      open={Boolean(group)}
      onOpenChange={(open) => {
        if (!open && !uploading) onClose();
      }}
    >
      <DialogContent className="package-upload-dialog">
        <DialogHeader>
          <DialogTitle>
            Atualizar pacote {group?.label}
          </DialogTitle>
          <DialogDescription>
            Um único GeoPackage será validado e distribuído automaticamente
            entre todas as fontes deste grupo.
          </DialogDescription>
        </DialogHeader>

          {(error || session?.status === "FAILED") && (
            <div className="source-dialog-error package-job-error">
              <TriangleAlert size={18} />
              <div>
                <strong>
                  {session?.error_title || "Falha no processamento"}
                </strong>

                <span>
                  {session?.error_detail ||
                    error ||
                    session?.error ||
                    "Não foi possível concluir o processamento do pacote."}
                </span>

                {session?.error_code && (
                  <small>Código: {session.error_code}</small>
                )}

                {session?.error_retryable && (
                  <small>
                    O arquivo foi preservado no servidor e pode ser
                    processado novamente sem novo upload.
                  </small>
                )}
              </div>
            </div>
          )}
        <div className="package-summary">
          <div>
            <small>ARQUIVO ESPERADO</small>
            <strong>{expectedPackage || "GeoPackage configurado"}</strong>
          </div>

          <div>
            <small>FONTES ATUALIZADAS</small>
            <strong>{group?.sources.length ?? 0}</strong>
          </div>
        </div>

        <div className="package-targets">
          {(group?.sources ?? []).map((source) => (
            <div key={source.id}>
              <CheckCircle2 size={15} />
              <span>
                <strong>{source.name}</strong>
                <small>
                  {String(source.metadata_json.source_layer ?? "Camada não definida")}
                </small>
              </span>
            </div>
          ))}
        </div>

        {!inspection?.valid && !processing && session?.status !== "READY" && (
          <>
            <label className="package-reference-date">
              <span>Data de referência</span>
              <input
                type="date"
                value={referenceDate}
                onChange={(event) => setReferenceDate(event.target.value)}
                disabled={uploading}
              />
            </label>

            <label className="source-vector-drop package-file-drop">
              <FileUp size={24} />
              <strong>
                {file ? file.name : "Selecionar GeoPackage"}
              </strong>
              <small>
                {file
                  ? `${(file.size / 1024 / 1024 / 1024).toFixed(2)} GB`
                  : expectedPackage || ".gpkg"}
              </small>
              <input
                type="file"
                accept=".gpkg"
                disabled={uploading}
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  setSession(null);
                  setProgress(0);
                  setPhase("");
                  setError(null);
                }}
              />
            </label>
          </>
        )}

          {(uploading || phase || processing || showJobProgress) && (
            <div className="package-progress package-job-progress">
              <div className="package-progress-heading">
                <span>
                  {session?.processing_stage ||
                    phase ||
                    (uploading
                      ? "Enviando GeoPackage…"
                      : "Processando pacote…")}
                </span>

                <strong>{uploading ? progress : jobProgress}%</strong>
              </div>

              <progress
                value={uploading ? progress : jobProgress}
                max={100}
              />

              {showJobProgress && jobStatus !== "READY" && (
                <div className="package-job-meta">
                  <span
                    className={`package-job-status ${jobStatus.toLowerCase()}`}
                  >
                    {jobStatus === "QUEUED"
                      ? "NA FILA"
                      : jobStatus === "PROCESSING"
                        ? "PROCESSANDO"
                        : jobStatus === "FAILED"
                          ? "FALHOU"
                          : jobStatus}
                  </span>

                  {session?.current_layer_index &&
                    session?.total_layers && (
                      <span>
                        Camada {session.current_layer_index} de{" "}
                        {session.total_layers}
                      </span>
                    )}
                </div>
              )}

              {showJobProgress &&
                (completedLayers.length > 0 ||
                  session?.current_source ||
                  mappings.length > 0) && (
                  <div className="package-job-layers">
                    {mappings.map((mapping) => {
                      const completed = completedSourceIds.has(
                        mapping.source_id,
                      );

                      const current =
                        !completed &&
                        session?.current_source === mapping.source_name;

                      const completedItem = completedLayers.find(
                        (item) => item.source_id === mapping.source_id,
                      );

                      const featureCount =
                        completedItem?.feature_count ??
                        (current
                          ? session?.current_layer_total_features
                          : null);

                      return (
                        <div
                          key={mapping.source_id}
                          className={`package-job-layer ${
                            completed
                              ? "completed"
                              : current
                                ? "current"
                                : "pending"
                          }`}
                        >
                          <span className="package-job-layer-icon">
                            {completed ? (
                              <CheckCircle2 size={17} />
                            ) : current ? (
                              <RefreshCw size={17} className="spin" />
                            ) : (
                              <span className="package-job-dot" />
                            )}
                          </span>

                          <div>
                            <strong>{mapping.source_name}</strong>
                            <small>{mapping.actual_layer}</small>

                            {featureCount != null &&
                              Number(featureCount) > 0 && (
                                <span>
                                  {Number(featureCount).toLocaleString("pt-BR")}{" "}
                                  feições
                                </span>
                              )}

                            {current && (
                              <em>
                                {session?.processing_stage ||
                                  "Processando camada…"}
                              </em>
                            )}

                            {completed && <em>Camada concluída</em>}

                            {!completed && !current && (
                              <em>Aguardando</em>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
            </div>
          )}
        {inspection && (
          <div
            className={`package-inspection ${
              inspection.valid ? "valid" : "invalid"
            }`}
          >
            <div className="package-inspection-title">
              {inspection.valid ? (
                <CheckCircle2 size={18} />
              ) : (
                <TriangleAlert size={18} />
              )}
              <strong>
                {inspection.valid
                  ? "GeoPackage validado"
                  : "GeoPackage incompleto"}
              </strong>
            </div>

            <div className="package-layer-list">
              {mappings.map((mapping) => (
                <div key={mapping.source_id}>
                  <CheckCircle2 size={14} />
                  <span>
                    {mapping.actual_layer}
                    <small>→ {mapping.source_name}</small>
                  </span>
                </div>
              ))}

              {(inspection.missing_layers ?? []).map((layer) => (
                <div className="missing" key={layer}>
                  <TriangleAlert size={14} />
                  <span>{layer}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {session?.status === "READY" && (
          <div className="package-ready">
            <CheckCircle2 size={22} />
            <div>
              <strong>Pacote processado com sucesso</strong>
              <span>
                As novas versões já estão ativas nas fontes correspondentes.
              </span>
            </div>
          </div>
        )}

          <div className="package-dialog-actions">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={uploading}
            >
              {processing
                ? "Fechar e continuar em segundo plano"
                : "Fechar"}
            </Button>

            {!inspection?.valid &&
              session?.status !== "READY" &&
              session?.status !== "FAILED" && (
                <Button
                  type="button"
                  onClick={() => void uploadPackage()}
                  disabled={!file || uploading || processing}
                >
                  {uploading ? (
                    <>
                      <RefreshCw size={15} className="spin" />
                      Enviando {progress}%
                    </>
                  ) : (
                    <>
                      <FileUp size={15} />
                      Enviar pacote
                    </>
                  )}
                </Button>
              )}

            {inspection?.valid &&
              session?.status !== "READY" &&
              session?.status !== "FAILED" &&
              !processing && (
                <Button
                  type="button"
                  onClick={() => void processPackage()}
                >
                  <Database size={15} />
                  Processar pacote
                </Button>
              )}

            {retryAvailable && !processing && (
              <Button
                type="button"
                onClick={() => void processPackage()}
              >
                <RefreshCw size={15} />
                Tentar processar novamente
              </Button>
            )}
          </div>
      </DialogContent>
    </Dialog>
  );
}


export function SourcesModule() {
  const [sources, setSources] = useState<Source[]>([]),
    [versions, setVersions] = useState<Record<string, SourceVersion | null>>(
      {},
    ),
    [loading, setLoading] = useState(true),
    [sigefCatalogueModified, setSigefCatalogueModified] = useState<string | null>(null),
    [syncing, setSyncing] = useState<string | null>(null),
    [editing, setEditing] = useState<Source | null>(null),
    [packageGroup, setPackageGroup] = useState<SourcePackageGroup | null>(null),
    [message, setMessage] = useState<{
      kind: "success" | "error";
      text: string;
    } | null>(null);
  const [customName, setCustomName] = useState(""),
    [customCategory, setCustomCategory] = useState("CAR_SICAR"),
    [customUf, setCustomUf] = useState("AP"),
    [customInstitution, setCustomInstitution] = useState(""),
    [customReferenceDate, setCustomReferenceDate] = useState(
      new Date().toISOString().slice(0, 10),
    ),
    [customSourceUrl, setCustomSourceUrl] = useState(""),
    [customNotes, setCustomNotes] = useState(""),
    [customFile, setCustomFile] = useState<File | null>(null),
    [customUploading, setCustomUploading] = useState(false),
    [customProgress, setCustomProgress] = useState(0),
    [customPhase, setCustomPhase] = useState(""),
    [customUploadSession, setCustomUploadSession] = useState<{
      source_id?: string;
      upload_id?: string;
      status?: string;
      filename?: string;
      file_size?: number;
      received_bytes?: number;
      progress_percent?: number;
      processing_stage?: string | null;
      error?: string | null;
      error_title?: string | null;
      error_detail?: string | null;
      error_retryable?: boolean;
      result?: {
        source_id?: string;
        source_name?: string;
        version_id?: string;
        feature_count?: number;
      };
    } | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/sources`);
      if (!response.ok)
        throw new Error("Não foi possível consultar as fontes.");
      const loaded: Source[] = await response.json();
      setSources(loaded);
      const pairs = await Promise.all(
        loaded.map(async (source) => {
          const result = await fetch(
            `${API_URL}/sources/${source.id}/versions`,
          );
          const history: SourceVersion[] = result.ok ? await result.json() : [];
          return [
            source.id,
            history.find((version) => version.is_current) ?? null,
          ] as const;
        }),
      );
      setVersions(Object.fromEntries(pairs));
      const nationalSigef = loaded.some((item) => item.slug === "incra-sigef-brasil");
      if (nationalSigef) {
        try {
          const metadataResponse = await fetch(`${API_URL}/sources/incra/sigef/metadata`, { credentials: "include" });
          const official = metadataResponse.ok ? await metadataResponse.json() : null;
          setSigefCatalogueModified(
            official?.available && typeof official.last_modified === "string"
              ? official.last_modified : null
          );
        } catch {
          setSigefCatalogueModified(null);
        }
      }
      setEditing((current) =>
        current
          ? (loaded.find((source) => source.id === current.id) ?? null)
          : null,
      );
    } catch (reason) {
      setMessage({
        kind: "error",
        text: reason instanceof Error ? reason.message : "Falha ao carregar.",
      });
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const official = useMemo(
    () => sources.filter((source) => source.is_official),
    [sources],
  );
  const custom = useMemo(
    () => sources.filter((source) => Boolean(source.metadata_json.custom_layer)),
    [sources],
  );

  const officialGroups = useMemo(() => {
    const groupOrder = [
      "ASSENTAMENTOS",
      "SIGEF",
      "SNCI",
      "QUILOMBOLAS",
      "ANM",
      "FUNAI",
      "IBAMA",
      "ICMBIO",
      "IPHAN",
      "SICAR",
      "SPU",
    ];

    const labels: Record<string, string> = {
      ASSENTAMENTOS: "Assentamentos",
      SIGEF: "SIGEF",
      SNCI: "SNCI",
      QUILOMBOLAS: "Quilombolas",
      ANM: "ANM",
      FUNAI: "FUNAI",
      IBAMA: "IBAMA",
      ICMBIO: "ICMBio",
      IPHAN: "IPHAN",
      SICAR: "SICAR",
      SPU: "SPU",
    };

    const grouped = new Map<string, Source[]>();

    for (const source of official) {
      const metadataGroup = String(
        source.metadata_json.source_group ?? "",
      ).trim();

      const institution = source.institution
        .trim()
        .toUpperCase()
        .replace("ICMBIO", "ICMBIO");

      const key = metadataGroup || institution || "OUTRAS";

      if (!grouped.has(key)) {
        grouped.set(key, []);
      }

      grouped.get(key)!.push(source);
    }

    return Array.from(grouped.entries())
      .map(([key, groupSources]) => ({
        key,
        label: labels[key] ?? key,
        sources: [...groupSources].sort((a, b) =>
          a.name.localeCompare(b.name, "pt-BR"),
        ),
      }))
      .sort((a, b) => {
        const ai = groupOrder.indexOf(a.key);
        const bi = groupOrder.indexOf(b.key);

        if (ai === -1 && bi === -1) {
          return a.label.localeCompare(b.label, "pt-BR");
        }

        if (ai === -1) return 1;
        if (bi === -1) return -1;

        return ai - bi;
      });
  }, [official]);
  const changed = async (text: string) => {
    setMessage({ kind: "success", text });
    await load();
  };
  const synchronize = async (source: Source) => {
    setSyncing(source.id);
    try {
      const response = await fetch(`${API_URL}/sources/${source.id}/sync`, {
        method: "POST",
      });
      const body = await response.json().catch(() => null);
      if (!response.ok)
        throw new Error(body?.detail ?? "Falha ao sincronizar.");
      await changed(
        `${source.name}: ${Number(body.feature_count).toLocaleString("pt-BR")} feições atualizadas.`,
      );
    } catch (reason) {
      setMessage({
        kind: "error",
        text:
          reason instanceof Error
            ? reason.message.slice(0, 600)
            : "Falha ao sincronizar.",
      });
    } finally {
      setSyncing(null);
    }
  };
  const pollCustomProcessing = async (
    sourceId: string,
    uploadId: string,
    resumeKey: string,
  ) => {
    for (;;) {
      const response = await fetch(
        `${API_URL}/sources/${sourceId}/uploads/${uploadId}/status`,
      );

      const body = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          body?.detail ?? "Não foi possível acompanhar o processamento.",
        );
      }

      setCustomUploadSession(body);

      const status = String(body?.status ?? "");

      const progress = Math.max(
        0,
        Math.min(
          100,
          Number(
            body?.progress_percent ??
              (status === "UPLOADING"
                ? Math.round(
                    (Number(body.received_bytes || 0) /
                      Math.max(Number(body.file_size || 1), 1)) *
                      100,
                  )
                : 99),
          ),
        ),
      );

      setCustomProgress(progress);
      setCustomPhase(
        body?.processing_stage ??
          (status === "QUEUED"
            ? "Aguardando processamento vetorial…"
            : status === "PROCESSING"
              ? "Importando vetor para o PostGIS…"
              : ""),
      );

      if (status === "READY") {
        window.localStorage.removeItem(resumeKey);

        const total = Number(body?.result?.feature_count || 0);
        const sourceName =
          body?.result?.source_name || customName.trim() || "Camada";

        setCustomProgress(100);
        setCustomPhase("Importação concluída.");

        setCustomName("");
        setCustomInstitution("");
        setCustomSourceUrl("");
        setCustomNotes("");
        setCustomFile(null);
        setCustomUploadSession(null);

        await changed(
          `${sourceName}: ${total.toLocaleString("pt-BR")} feições importadas e ativadas.`,
        );

        window.dispatchEvent(
          new CustomEvent("amazonika:sources-changed"),
        );

        return;
      }

      if (status === "FAILED") {
        setMessage({
          kind: "error",
          text:
            body?.error_detail ??
            body?.error ??
            "O processamento vetorial falhou. O arquivo foi preservado.",
        });

        return;
      }

      await new Promise((resolve) =>
        window.setTimeout(resolve, 3000),
      );
    }
  };

  const addCustomLayer = async (event: FormEvent) => {
    event.preventDefault();

    if (!customFile) return;

    const CHUNK_SIZE = 25 * 1024 * 1024;

    const resumeKey =
      `amazonika-custom-upload:` +
      `${customUf}:${customCategory}:` +
      `${customFile.name}:${customFile.size}:` +
      `${customName.trim()}`;

    setCustomUploading(true);
    setCustomProgress(0);
    setCustomPhase("Preparando upload…");
    setMessage(null);

    try {
      let sourceId = "";
      let uploadId = "";
      let offset = 0;

      const previous =
        window.localStorage.getItem(resumeKey);

      if (previous) {
        try {
          const saved = JSON.parse(previous);

          sourceId = String(saved?.source_id || "");
          uploadId = String(saved?.upload_id || "");

          if (sourceId && uploadId) {
            const statusResponse = await fetch(
              `${API_URL}/sources/${sourceId}/uploads/${uploadId}/status`,
            );

            if (statusResponse.ok) {
              const status = await statusResponse.json();

              const sameFile =
                Number(status.file_size) === customFile.size &&
                status.filename === customFile.name;

              if (!sameFile) {
                sourceId = "";
                uploadId = "";
                window.localStorage.removeItem(resumeKey);
              } else if (status.status === "UPLOADING") {
                offset = Number(status.received_bytes || 0);

                setCustomProgress(
                  Math.min(
                    99,
                    Math.round(
                      (offset / customFile.size) * 100,
                    ),
                  ),
                );

                setCustomPhase(
                  `Retomando upload em ${Math.round(
                    (offset / customFile.size) * 100,
                  )}%…`,
                );
              } else if (
                status.status === "QUEUED" ||
                status.status === "PROCESSING"
              ) {
                setCustomUploadSession(status);

                await pollCustomProcessing(
                  sourceId,
                  uploadId,
                  resumeKey,
                );

                return;
              } else if (status.status === "FAILED") {
                setCustomUploadSession(status);
                setCustomProgress(
                  Number(status.progress_percent || 99),
                );
                setCustomPhase(
                  status.processing_stage ||
                    "Falha no processamento.",
                );

                setMessage({
                  kind: "error",
                  text:
                    status.error_detail ||
                    status.error ||
                    "O processamento falhou. O arquivo permanece no servidor.",
                });

                return;
              } else if (status.status === "READY") {
                window.localStorage.removeItem(resumeKey);
                await load();
                return;
              }
            } else {
              sourceId = "";
              uploadId = "";
              window.localStorage.removeItem(resumeKey);
            }
          }
        } catch {
          sourceId = "";
          uploadId = "";
          window.localStorage.removeItem(resumeKey);
        }
      }

      // A fonte é criada apenas uma vez.
      if (!sourceId) {
        setCustomPhase("Criando camada territorial…");

        const registerResponse = await fetch(
          `${API_URL}/sources/custom-vector/register`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              name: customName.trim(),
              category: customCategory,
              uf: customUf,
              institution:
                customInstitution.trim() || null,
              source_url:
                customSourceUrl.trim() || null,
              notes:
                customNotes.trim() || null,
            }),
          },
        );

        const registered =
          await registerResponse.json().catch(() => null);

        if (!registerResponse.ok) {
          throw new Error(
            registered?.detail ??
              "Não foi possível cadastrar a camada.",
          );
        }

        sourceId = String(registered.source.id);

        window.localStorage.setItem(
          resumeKey,
          JSON.stringify({
            source_id: sourceId,
          }),
        );
      }

      // Cria a sessão de upload somente uma vez.
      if (!uploadId) {
        setCustomPhase("Criando sessão de upload…");

        const startResponse = await fetch(
          `${API_URL}/sources/${sourceId}/uploads/start`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              filename: customFile.name,
              file_size: customFile.size,
              reference_date: customReferenceDate,
              layer_name: null,
            }),
          },
        );

        const started =
          await startResponse.json().catch(() => null);

        if (!startResponse.ok) {
          throw new Error(
            started?.detail ??
              "Não foi possível iniciar o upload.",
          );
        }

        uploadId = String(started.upload_id);
        offset = Number(started.received_bytes || 0);

        window.localStorage.setItem(
          resumeKey,
          JSON.stringify({
            source_id: sourceId,
            upload_id: uploadId,
          }),
        );

        setCustomUploadSession(started);
      }

      setCustomPhase(
        offset > 0
          ? "Retomando envio do arquivo…"
          : "Enviando arquivo…",
      );

      while (offset < customFile.size) {
        const endOffset = Math.min(
          offset + CHUNK_SIZE,
          customFile.size,
        );

        const blob = customFile.slice(
          offset,
          endOffset,
        );

        const data = new FormData();

        data.append("offset", String(offset));
        data.append(
          "chunk",
          blob,
          `${customFile.name}.part`,
        );

        const chunkResponse = await fetch(
          `${API_URL}/sources/${sourceId}/uploads/${uploadId}/chunk`,
          {
            method: "POST",
            body: data,
          },
        );

        const chunkBody =
          await chunkResponse.json().catch(() => null);

        if (!chunkResponse.ok) {
          // Se houve perda de conexão ou repetição de chunk,
          // consulta o servidor e continua do byte efetivamente salvo.
          if (chunkResponse.status === 409) {
            const statusResponse = await fetch(
              `${API_URL}/sources/${sourceId}/uploads/${uploadId}/status`,
            );

            if (statusResponse.ok) {
              const status =
                await statusResponse.json();

              offset = Number(
                status.received_bytes || offset,
              );

              setCustomProgress(
                Math.min(
                  99,
                  Math.round(
                    (offset / customFile.size) * 100,
                  ),
                ),
              );

              continue;
            }
          }

          throw new Error(
            chunkBody?.detail ??
              "Falha durante o envio. Selecione novamente o mesmo arquivo para continuar.",
          );
        }

        offset = Number(
          chunkBody.received_bytes || 0,
        );

        setCustomProgress(
          Math.min(
            99,
            Math.round(
              (offset / customFile.size) * 100,
            ),
          ),
        );
      }

      setCustomPhase(
        "Upload concluído. Enviando para processamento…",
      );

      const completeResponse = await fetch(
        `${API_URL}/sources/${sourceId}/uploads/${uploadId}/complete`,
        {
          method: "POST",
        },
      );

      const completed =
        await completeResponse.json().catch(() => null);

      if (!completeResponse.ok) {
        throw new Error(
          completed?.detail ??
            "Não foi possível finalizar o upload.",
        );
      }

      setCustomUploadSession(completed);
      setCustomProgress(
        Number(completed.progress_percent || 99),
      );
      setCustomPhase(
        completed.processing_stage ||
          "Aguardando processamento vetorial…",
      );

      await pollCustomProcessing(
        sourceId,
        uploadId,
        resumeKey,
      );
    } catch (reason) {
      setMessage({
        kind: "error",
        text:
          reason instanceof Error
            ? reason.message
            : "Falha durante o upload da camada adicional.",
      });

      setCustomPhase(
        "Upload interrompido. O progresso salvo será reutilizado na próxima tentativa.",
      );
    } finally {
      setCustomUploading(false);
    }
  };

  const retryCustomProcessing = async () => {
    const sourceId =
      customUploadSession?.source_id;
    const uploadId =
      customUploadSession?.upload_id;

    if (!sourceId || !uploadId || !customFile) {
      return;
    }

    const resumeKey =
      `amazonika-custom-upload:` +
      `${customUf}:${customCategory}:` +
      `${customFile.name}:${customFile.size}:` +
      `${customName.trim()}`;

    setCustomUploading(true);
    setMessage(null);
    setCustomPhase("Solicitando reprocessamento…");

    try {
      const response = await fetch(
        `${API_URL}/sources/${sourceId}/uploads/${uploadId}/retry`,
        {
          method: "POST",
        },
      );

      const body =
        await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          body?.detail ??
            "Não foi possível reiniciar o processamento.",
        );
      }

      setCustomUploadSession(body);

      await pollCustomProcessing(
        sourceId,
        uploadId,
        resumeKey,
      );
    } catch (reason) {
      setMessage({
        kind: "error",
        text:
          reason instanceof Error
            ? reason.message
            : "Falha ao reprocessar a camada.",
      });
    } finally {
      setCustomUploading(false);
    }
  };

  const toggleCustomLayer=async(source:Source,checked:boolean)=>{
    try {
      const response=await fetch(`${API_URL}/sources/${source.id}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({is_active:checked})});
      const body=await response.json().catch(()=>null);
      if(!response.ok) throw new Error(body?.detail ?? "Não foi possível alterar a visibilidade.");
      await load(); window.dispatchEvent(new CustomEvent("amazonika:sources-changed"));
    } catch(reason) { setMessage({kind:"error",text:reason instanceof Error?reason.message:"Falha ao alterar a camada."}); }
  };
  const configured = official.filter((source) =>
    Boolean(
      source.service_url ||
      (source.metadata_json.wms_enabled && source.metadata_json.wms_theme),
    ),
  ).length;
  return (
    <section className="sources-module">
      <div className="sources-hero">
        <div>
          <p className="eyebrow">CATÁLOGO TERRITORIAL</p>
          <h2>Fontes oficiais</h2>
          <p>
            WMS oficial para consulta visual e vetores versionados para análises
            e relatórios.
          </p>
        </div>
        <Button
          className="sources-refresh"
          onClick={() => void load()}
          disabled={loading}
        >
          <RefreshCw size={16} className={loading ? "spin" : ""} /> Atualizar
          painel
        </Button>
      </div>
      <div className="sources-summary">
        <article>
          <span className="status-icon blue">
            <Database size={19} />
          </span>
          <div>
            <small>FONTES OFICIAIS</small>
            <strong>{official.length}</strong>
          </div>
        </article>
        <article>
          <span className="status-icon green">
            <Server size={19} />
          </span>
          <div>
            <small>SERVIÇOS CONFIGURADOS</small>
            <strong>{configured}</strong>
          </div>
        </article>
        <article>
          <span className="status-icon amber">
            <RefreshCw size={19} />
          </span>
          <div>
            <small>VETORES ATUALIZADOS</small>
            <strong>
              {
                Object.entries(versions).filter(([id, version]) => {
                  const source = sources.find((item) => item.id === id);
                  return (
                    version &&
                    versionAge(version) !== null &&
                    (versionAge(version) ?? 999) <=
                      Number(source?.metadata_json.stale_after_days ?? 15)
                  );
                }).length
              }
            </strong>
          </div>
        </article>
      </div>
      {message && (
        <div className={`sources-message ${message.kind}`}>
          {message.kind === "success" ? (
            <CheckCircle2 size={18} />
          ) : (
            <TriangleAlert size={18} />
          )}
          <span>{message.text}</span>
        </div>
      )}
      <div className="source-groups">
        {officialGroups.map((group) => (
          <section className="source-group" key={group.key}>
            <div className="source-group-heading">
              <div>
                <p className="eyebrow">FONTE OFICIAL</p>
                <h2>{group.label}</h2>
              </div>
              <div className="source-group-actions">
                <span>
                  {group.sources.length}{" "}
                  {group.sources.length === 1 ? "fonte" : "fontes"}
                </span>

                {["ASSENTAMENTOS", "SIGEF", "SNCI"].includes(group.key) && (
                  <Button
                    type="button"
                    className="source-package-button"
                    onClick={() => setPackageGroup(group)}
                  >
                    <FileUp size={14} />
                    {group.key === "ASSENTAMENTOS"
                      ? "Atualizar pacote"
                      : `Importar pacote ${group.label}`}
                  </Button>
                )}
              </div>
            </div>

            <div className="source-card-grid">
              {group.sources.map((source) => {
          const version = versions[source.id],
            age = versionAge(version),
            limit = Number(source.metadata_json.stale_after_days ?? 15),
            stale = !version || age === null || age > limit,
            wms = Boolean(
              source.metadata_json.wms_enabled &&
              source.metadata_json.wms_theme,
            ),
            packageManaged = ["ASSENTAMENTOS", "SIGEF", "SNCI"].includes(
              String(source.metadata_json.source_group ?? ""),
            ),
            vectorOnDemand =
              !packageManaged &&
              Boolean(
                source.metadata_json.wfs_on_demand ||
                  source.metadata_json.arcgis_on_demand,
              ),
            connected = wms || Boolean(version),
            automatic = Boolean(
              !packageManaged &&
              source.service_url &&
              source.layer_name &&
              ["WFS", "ARCGIS_FEATURE"].includes(source.kind) &&
              !vectorOnDemand,
            );
          return (
            <article
              className={`source-card ${stale ? "stale" : ""}`}
              key={source.id}
            >
              <header>
                <span
                  className={`source-state ${connected ? "ready" : "stale"}`}
                  title={connected ? "Fonte oficial conectada" : "Fonte sem conexão ou carga"}
                />
                <div>
                  <small>{source.institution}</small>
                  <h3>{source.name}</h3>
                </div>
                {stale && (
                  <span className="source-stale-badge">
                    {packageManaged
                      ? stale
                        ? "ATUALIZAR PACOTE"
                        : "VETOR LOCAL"
                      : vectorOnDemand
                        ? "VETOR SOB DEMANDA"
                        : wms
                          ? "VETOR PENDENTE"
                          : "ATUALIZAR"}
                  </span>
                )}
              </header>
              <dl>
                <div>
                  <dt>Base vetorial</dt>
                  <dd>
                    {!version
                      ? packageManaged
                        ? "Sem carga"
                        : vectorOnDemand
                          ? "Gerada ao identificar/analisar"
                          : "Sem carga"
                      : stale
                        ? `Desatualizada${age !== null ? ` há ${age} dias` : ""}`
                        : "Atualizada"}
                  </dd>
                </div>
                <div>
                  <dt>Feições</dt>
                  <dd>
                    {version
                      ? version.feature_count.toLocaleString("pt-BR")
                      : "—"}
                  </dd>
                </div>
                <div>
                  <dt>Última importação local</dt>
                  <dd>{formatDate(version?.imported_at)}</dd>
                </div>
                {version?.reference_date && (
                  <div>
                    <dt>Referência dos dados locais</dt>
                    <dd>{new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" }).format(new Date(`${version.reference_date}T00:00:00Z`))}</dd>
                  </div>
                )}
                {wms && (
                  <div>
                    <dt>{source.slug === "incra-sigef-brasil" ? "Última modificação no catálogo GeoNode" : "Atualização do serviço WMS"}</dt>
                    <dd>{source.slug === "incra-sigef-brasil" && sigefCatalogueModified
                      ? formatDate(sigefCatalogueModified)
                      : "Não informada pelo serviço"}</dd>
                  </div>
                )}
                <div>
                  <dt>Frequência</dt>
                  <dd>{formatFrequency(source.update_frequency)}</dd>
                </div>
                {wms && (
                  <div>
                    <dt>Conexão oficial</dt>
                    <dd className="source-wms-connected">WMS configurado · consulte o teste de conexão</dd>
                  </div>
                )}
                {packageManaged && (
                  <div>
                    <dt>Análise vetorial</dt>
                    <dd className="source-wms-connected">
                      Vetor nacional local
                    </dd>
                  </div>
                )}

                {!packageManaged && vectorOnDemand && (
                  <div>
                    <dt>Análise vetorial</dt>
                    <dd className="source-wms-connected">
                      {source.metadata_json.arcgis_on_demand
                        ? "ArcGIS REST automático por área"
                        : "WFS automático por UF e área"}
                    </dd>
                  </div>
                )}
                {Array.isArray(source.metadata_json.wfs_layers) && (
                  <div>
                    <dt>Conjunto oficial</dt>
                    <dd className="source-wms-connected">
                      {source.metadata_json.wfs_layers.length} camadas SPU agregadas
                    </dd>
                  </div>
                )}
              </dl>
              <footer>
                {automatic ? (
                  <Button
                    onClick={() => void synchronize(source)}
                    disabled={syncing !== null}
                  >
                    <RefreshCw
                      size={14}
                      className={syncing === source.id ? "spin" : ""}
                    />{" "}
                    {version ? "Sincronizar" : "Primeira carga"}
                  </Button>
                ) : (
                  <span>
                    {packageManaged
                      ? "Vetor nacional · atualização por pacote"
                      : vectorOnDemand
                        ? source.metadata_json.arcgis_on_demand
                          ? "WMS + ArcGIS REST sob demanda"
                          : "WMS + WFS sob demanda"
                        : wms
                          ? "WMS ativo · vetor local"
                          : "Importação manual"}
                  </span>
                )}
                <button
                  className="source-settings-button"
                  onClick={() => setEditing(source)}
                  title={`Configurar ${source.name}`}
                >
                  <Settings size={16} />
                </button>
              </footer>
            </article>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      <section className="custom-sources-section">
        <div className="custom-sources-heading">
          <div><p className="eyebrow">CAMADAS COMPLEMENTARES</p><h2>Vetores adicionais por UF</h2></div>
          <p>Cadastre CAR/SICAR, SPU, assentamentos, unidades de conservação e outras bases territoriais por UF. Toda nova camada entra ligada por padrão no mapa e poderá participar da análise enquanto permanecer ligada.</p>
        </div>
        <form className="custom-source-form" onSubmit={addCustomLayer}>
          <label><span>Nome da camada</span><input required minLength={3} value={customName} onChange={(e)=>setCustomName(e.target.value)} placeholder="Ex.: Assentamentos estaduais do Amapá" /></label>
          <label>
            <span>Categoria</span>
            <select value={customCategory} onChange={(e)=>setCustomCategory(e.target.value)}>
              <option value="CAR_SICAR">CAR / SICAR</option>
              <option value="SPU">SPU - Patrimônio da União</option>
              <option value="ASSENTAMENTO_ESTADUAL">Assentamento estadual</option>
              <option value="ASSENTAMENTO_MUNICIPAL">Assentamento municipal</option>
              <option value="UC_ESTADUAL">UC estadual</option>
              <option value="UC_MUNICIPAL">UC municipal</option>
              <option value="AMBIENTAL_ESTADUAL">Outra base ambiental estadual</option>
              <option value="FUNDIARIO_ESTADUAL">Outra base fundiária estadual</option>
              <option value="OUTRO">Outro vetor territorial</option>
            </select>
          </label>
          <label><span>UF</span><select value={customUf} onChange={(e)=>setCustomUf(e.target.value)}>{["AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA","PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO"].map((uf)=><option key={uf}>{uf}</option>)}</select></label>
          <label>
            <span>Órgão / origem</span>
            <input
              value={customInstitution}
              onChange={(e)=>setCustomInstitution(e.target.value)}
              placeholder={customCategory==="SPU" ? "Ex.: SPU" : customCategory==="CAR_SICAR" ? "Ex.: SEMA/AP ou SICAR" : "Ex.: SEMA/AP"}
            />
          </label>
          <label>
            <span>Data de referência</span>
            <input
              required
              type="date"
              value={customReferenceDate}
              onChange={(e)=>setCustomReferenceDate(e.target.value)}
            />
          </label>
          <label>
            <span>Fonte / endereço oficial (opcional)</span>
            <input
              type="url"
              value={customSourceUrl}
              onChange={(e)=>setCustomSourceUrl(e.target.value)}
              placeholder="https://..."
            />
          </label>
          <label>
            <span>Observação (opcional)</span>
            <input
              value={customNotes}
              onChange={(e)=>setCustomNotes(e.target.value)}
              placeholder="Ex.: Base vetorial oficial publicada em setembro/2026"
            />
          </label>
          <label className="custom-file-field">
            <span>Arquivo vetorial ou KML</span>
            <input
              required
              type="file"
              accept=".gpkg,.kml,.geojson,.json,.zip"
              onChange={(e)=>{
                setCustomFile(e.target.files?.[0]??null);
                setCustomProgress(0);
                setCustomPhase("");
                setCustomUploadSession(null);
                setMessage(null);
              }}
            />
            <small>GeoPackage, KML, GeoJSON ou Shapefile ZIP · convertido para SIRGAS 2000</small>
          </label>
          {(customUploading || customPhase || customProgress > 0) && (
            <div
              style={{
                gridColumn: "1 / -1",
                display: "grid",
                gap: 6,
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 12,
                  fontSize: 12,
                }}
              >
                <span>
                  {customUploadSession?.processing_stage ||
                    customPhase ||
                    "Processando…"}
                </span>
                <strong>{customProgress}%</strong>
              </div>

              <progress
                max={100}
                value={customProgress}
                style={{
                  width: "100%",
                  height: 10,
                }}
              />
            </div>
          )}

          {customUploadSession?.status === "FAILED" &&
          customUploadSession.error_retryable ? (
            <Button
              type="button"
              disabled={customUploading}
              onClick={() =>
                void retryCustomProcessing()
              }
            >
              {customUploading ? (
                <RefreshCw
                  size={15}
                  className="spin"
                />
              ) : (
                <RefreshCw size={15} />
              )}
              Tentar processar novamente
            </Button>
          ) : (
            <Button
              disabled={
                customUploading || !customFile
              }
            >
              {customUploading ? (
                <RefreshCw
                  size={15}
                  className="spin"
                />
              ) : (
                <FileUp size={15} />
              )}
              {customUploading
                ? customProgress < 99
                  ? `Enviando ${customProgress}%`
                  : "Processando…"
                : customProgress > 0 &&
                    customProgress < 100
                  ? `Continuar de ${customProgress}%`
                  : "Adicionar camada ligada"}
            </Button>
          )}
        </form>
        {custom.length>0&&<div className="custom-source-list">{custom.map((source)=>{const version=versions[source.id]; return <article key={source.id}><div><small>{String(source.metadata_json.custom_category_label??"Camada adicional")} · {String(source.metadata_json.scope_uf??"—")}</small><strong>{source.name}</strong><span>
  {source.institution}
  {version?.reference_date ? ` · ref. ${new Intl.DateTimeFormat("pt-BR").format(new Date(`${version.reference_date}T12:00:00`))}` : ""}
  {version ? ` · ${version.feature_count.toLocaleString("pt-BR")} feições` : " · Sem versão"}
</span></div><label><Switch className="source-config-switch" checked={source.is_active} onCheckedChange={(checked)=>void toggleCustomLayer(source,checked)} /><span>{source.is_active?"Ligada":"Desligada"}</span></label></article>})}</div>}
      </section>
      <PackageUploadDialog
        group={packageGroup}
        onClose={() => setPackageGroup(null)}
        onCompleted={changed}
      />

      <SourceSettingsDialog
        source={editing}
        onClose={() => setEditing(null)}
        onChanged={changed}
      />
    </section>
  );
}
