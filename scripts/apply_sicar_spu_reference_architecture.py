from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"ERRO [{label}]: bloco não localizado em {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"OK [{label}] - {path}")


# ============================================================
# 1. GEO-MAP: PostGIS/MVT sempre operacional; WMS só referência
# ============================================================
geo = Path("components/geo-map.tsx")
text = geo.read_text(encoding="utf-8")

old = '''      // Fontes oficiais particionadas que já possuem WMS permanecem
      // exclusivamente no serviço oficial enquanto a cópia vetorial
      // local não estiver completa. O SIGEF interno da Amazônika,
      // que não depende desse WMS, continua usando MVT local.
      const useOfficialWmsOnly =
        (layer.source === "SICAR" ||
          layer.source === "SPU") &&
        layer.wmsEnabled &&
        layer.wmsTheme;

      if (useOfficialWmsOnly) {
        const staleVectorTile = vectorTileLayersRef.current.get(layer.id);
        if (staleVectorTile) {
          staleVectorTile.getSource()?.clear();
          map.removeLayer(staleVectorTile);
          vectorTileLayersRef.current.delete(layer.id);
        }
        continue;
      }

'''
if old not in text:
    raise SystemExit("ERRO [geo-wms-only]: bloco useOfficialWmsOnly não localizado")
text = text.replace(
    old,
    '''      // O vetor local/PostGIS é sempre a camada operacional do sistema.
      // O WMS, quando habilitado, é apenas uma referência visual adicional.

''',
    1,
)

start_marker = '''      /*
       * Fallback 2:
       * fontes que existam somente como WMS no local clicado.
'''
end_marker = '''    };
    map.on("singleclick", identifyAtPixel);'''
start = text.find(start_marker)
end = text.find(end_marker, start)
if start == -1 or end == -1:
    raise SystemExit("ERRO [geo-identify-wms]: fallback WMS de identificação não localizado")
text = (
    text[:start]
    + '''      // WMS é somente referência visual. A ferramenta Identificar
      // trabalha exclusivamente com geometrias vetoriais presentes no PostGIS.
      setIdentifiedFeature(null);
'''
    + text[end:]
)
geo.write_text(text, encoding="utf-8")
print("OK [geo-map] - PostGIS/MVT prioritário e WMS somente visual")


# ============================================================
# 2. SOURCES MODULE: SICAR/SPU com a mesma janela WMS de referência
# ============================================================
sources = Path("components/sources-module.tsx")
text = sources.read_text(encoding="utf-8")

old = '''  const isIncra = source?.institution.toUpperCase() === "INCRA";
'''
new = '''  const institution = source?.institution.toUpperCase() ?? "";
  const isIncra = institution === "INCRA";
  const isSicar = institution === "SICAR";
  const isSpu = institution === "SPU";
  const isWmsReference = isIncra || isSicar || isSpu;
'''
if old not in text:
    raise SystemExit("ERRO [sources-reference-flags]: isIncra não localizado")
text = text.replace(old, new, 1)

old = '''    setAllowLegacy(Boolean(source.metadata_json.allow_insecure_tls));
'''
new = '''    setAllowLegacy(
      isIncra && Boolean(source.metadata_json.allow_insecure_tls),
    );
'''
if old not in text:
    raise SystemExit("ERRO [sources-legacy-state]: allowLegacy não localizado")
text = text.replace(old, new, 1)

old = '''      const payload = isIncra
        ? {
            kind: "DOWNLOAD",
            service_url: null,
            layer_name: null,
            update_frequency: frequency,
            wms_url: wmsUrl || null,
            wms_layer: wmsLayer || null,
            wms_enabled: wmsEnabled,
            allow_insecure_tls: allowLegacy,
            stale_after_days: 15,
            requires_auth: false,
            access_mode: "PUBLIC_WMS",
            service_role: "WMS_REFERENCE_WITH_VECTOR_SNAPSHOT",
          }
'''
new = '''      const payload = isWmsReference
        ? {
            kind: "DOWNLOAD",
            service_url: null,
            layer_name: null,
            update_frequency: frequency,
            wms_url: wmsUrl || null,
            wms_layer: wmsLayer || null,
            wms_enabled: wmsEnabled,
            allow_insecure_tls: isIncra ? allowLegacy : false,
            stale_after_days: 15,
            requires_auth: false,
            access_mode: "PUBLIC_WMS",
            service_role: isIncra
              ? "WMS_REFERENCE_WITH_VECTOR_SNAPSHOT"
              : "WMS_REFERENCE",
          }
'''
if old not in text:
    raise SystemExit("ERRO [sources-save-payload]: payload de referência não localizado")
text = text.replace(old, new, 1)

old = '''                {isIncra
                  ? "Visualização oficial WMS"
                  : "Conexão automática vetorial"}
'''
new = '''                {isWmsReference
                  ? "Visualização oficial WMS"
                  : "Conexão automática vetorial"}
'''
if old not in text:
    raise SystemExit("ERRO [sources-heading]: título da conexão não localizado")
text = text.replace(old, new, 1)

old = '''                {isIncra
                  ? "Serviço público do Acervo Fundiário, sem autenticação"
                  : "WFS ou ArcGIS FeatureServer"}
'''
new = '''                {isWmsReference
                  ? "Serviço oficial usado somente como referência visual"
                  : "WFS ou ArcGIS FeatureServer"}
'''
if old not in text:
    raise SystemExit("ERRO [sources-subheading]: subtítulo da conexão não localizado")
text = text.replace(old, new, 1)

# Somente a primeira condição controla o corpo principal da configuração.
old = '''          {isIncra ? (
            <>
'''
new = '''          {isWmsReference ? (
            <>
'''
if old not in text:
    raise SystemExit("ERRO [sources-reference-form]: formulário INCRA não localizado")
text = text.replace(old, new, 1)

old = '''                <div className="source-switch-field wide">
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
'''
new = '''                {isIncra && (
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
'''
if old not in text:
    raise SystemExit("ERRO [sources-legacy-switch]: switch legado não localizado")
text = text.replace(old, new, 1)

old = '''              <div className="wms-reference-warning">
                <Globe2 size={16} />
                <span>
                  O gov.br serve apenas para consultar/copiar URLs. O WMS
                  funciona sem login. A exceção legada fica restrita a{" "}
                  <strong>acervofundiario.incra.gov.br</strong>.
                </span>
              </div>
'''
new = '''              <div className="wms-reference-warning">
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
'''
if old not in text:
    raise SystemExit("ERRO [sources-reference-warning]: aviso WMS não localizado")
text = text.replace(old, new, 1)

text = text.replace(
    "WMS oficial do Amapá conectado",
    "WMS oficial conectado",
    1,
)
text = text.replace(
    "Testar conexão WMS do Amapá",
    "Testar conexão WMS oficial",
    1,
)

old = '''        {["ASSENTAMENTOS", "SIGEF", "SNCI"].includes(
          String(source?.metadata_json.source_group ?? ""),
        ) ? (
          <div className="source-package-managed-note">
            <Database size={17} />
            <div>
              <strong>Atualização controlada por pacote</strong>
              <small>
                Esta fonte faz parte de um GeoPackage composto. Use o botão
                de atualização no cabeçalho do grupo para manter todas as
                camadas sincronizadas.
              </small>
            </div>
          </div>
'''
new = '''        {isWmsReference || ["ASSENTAMENTOS", "SIGEF", "SNCI"].includes(
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
'''
if old not in text:
    raise SystemExit("ERRO [sources-vector-note]: nota de vetor não localizada")
text = text.replace(old, new, 1)

sources.write_text(text, encoding="utf-8")
print("OK [sources-module] - SICAR/SPU convertidos para WMS de referência")


# ============================================================
# 3. BACKEND: ao salvar SICAR/SPU como referência, mata legado/WFS
# ============================================================
route = Path("backend/app/api/routes/sources.py")
text = route.read_text(encoding="utf-8")
old = '''    for field,value in changes.items(): setattr(source,field,value)
    source.metadata_json=metadata
    db.commit(); db.refresh(source); return source
'''
new = '''    for field,value in changes.items(): setattr(source,field,value)

    # SICAR e SPU oficiais podem manter WMS como referência visual, mas
    # nunca devem acionar WFS/ArcGIS sob demanda nem TLS legado para a
    # operação territorial. O vetor operacional vem das cargas por UF.
    if (
        source.institution.upper() in {"SICAR", "SPU"}
        and metadata.get("service_role") == "WMS_REFERENCE"
    ):
        metadata["wfs_on_demand"] = False
        metadata["arcgis_on_demand"] = False
        metadata["allow_insecure_tls"] = False
        metadata["allow_legacy_tls"] = False
        source.service_url = None
        source.layer_name = None
        source.kind = SourceKind.DOWNLOAD

    source.metadata_json=metadata
    db.commit(); db.refresh(source); return source
'''
if old not in text:
    raise SystemExit("ERRO [backend-source-normalization]: update_source não localizado")
route.write_text(text.replace(old, new, 1), encoding="utf-8")
print("OK [sources.py] - normalização SICAR/SPU implementada")


# ============================================================
# 4. ANALISADOR: fontes WMS_REFERENCE nunca entram no cálculo
# ============================================================
analyzer = Path("backend/app/services/analyzer.py")
text = analyzer.read_text(encoding="utf-8")
old = '''    for source in db.scalars(selected_sources).all():
        metadata=dict(source.metadata_json or {})
        version=None
        access_mode="LOCAL_VECTOR"
'''
new = '''    for source in db.scalars(selected_sources).all():
        metadata=dict(source.metadata_json or {})

        # Fonte oficial marcada como WMS_REFERENCE é apenas cartográfica.
        # A análise usa exclusivamente as bases vetoriais PostGIS escolhidas
        # pelo usuário (incluindo CAR/SPU carregados por UF).
        if metadata.get("service_role") == "WMS_REFERENCE":
            continue

        version=None
        access_mode="LOCAL_VECTOR"
'''
if old not in text:
    raise SystemExit("ERRO [analyzer-reference-skip]: loop do analisador não localizado")
analyzer.write_text(text.replace(old, new, 1), encoding="utf-8")
print("OK [analyzer.py] - WMS_REFERENCE excluído da análise")

print("\nMIGRAÇÃO DE CÓDIGO CONCLUÍDA")
