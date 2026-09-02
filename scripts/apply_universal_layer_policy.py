from pathlib import Path
import runpy


# ============================================================
# 1. PATCH-BASE — aplicar somente se ainda não estiver presente
# ============================================================
geo = Path("components/geo-map.tsx")
sources = Path("components/sources-module.tsx")

g = geo.read_text(encoding="utf-8")
s = sources.read_text(encoding="utf-8")

base_applied = (
    "previousLayerStateRef" in g
    and "layerTransition" in g
    and "map-layer-transition" in g
    and "source-reference-badge" in s
)

if base_applied:
    print("OK [base-policy] - patch anterior já estava aplicado; não será repetido")
else:
    print("INFO [base-policy] - aplicando patch-base de feedback visual e cards")
    runpy.run_path(
        "scripts/apply_layer_loading_and_reference_cards.py",
        run_name="__main__",
    )
    s = sources.read_text(encoding="utf-8")


# ============================================================
# 2. POLÍTICA UNIVERSAL — sem regras operacionais por órgão
# ============================================================
old = '''            referenceOnly =
              source.metadata_json.service_role === "WMS_REFERENCE" &&
              ["SICAR", "SPU"].includes(source.institution.toUpperCase()),
            operationalVectors = referenceOnly
              ? custom.filter((item) => {
                  const category = String(item.metadata_json.custom_category ?? "");
                  return source.institution.toUpperCase() === "SICAR"
                    ? category === "CAR_SICAR"
                    : category === "SPU";
                })
              : [],
'''

new = '''            referenceOnly = String(
              source.metadata_json.service_role ?? "",
            ).startsWith("WMS_REFERENCE"),
            operationalKeys = (() => {
              const explicit = source.metadata_json.operational_categories;

              if (Array.isArray(explicit)) {
                return explicit.map((value) => String(value).toUpperCase());
              }

              const taxonomy = [
                String(source.metadata_json.source_group ?? ""),
                source.institution,
                source.name,
                source.slug,
              ]
                .join(" ")
                .toUpperCase();

              // Compatibilidade para bases já existentes. Novas fontes devem
              // preferencialmente declarar operational_categories ou seus
              // vetores declarar reference_source_id, sem exigir mudança de código.
              if (/CAR|SICAR/.test(taxonomy)) return ["CAR_SICAR"];
              if (/SPU|PATRIMÔNIO DA UNIÃO|PATRIMONIO DA UNIAO/.test(taxonomy)) {
                return ["SPU"];
              }

              const group = String(
                source.metadata_json.source_group ?? source.institution ?? "",
              ).toUpperCase();

              return group ? [group] : [];
            })(),
            operationalVectors = referenceOnly
              ? custom.filter((item) => {
                  const referenceSourceId = String(
                    item.metadata_json.reference_source_id ?? "",
                  );
                  const category = String(
                    item.metadata_json.custom_category ?? "",
                  ).toUpperCase();

                  return (
                    referenceSourceId === source.id ||
                    operationalKeys.includes(category)
                  );
                })
              : [],
'''

universal_marker = 'referenceSourceId === source.id ||'

if universal_marker in s:
    print("OK [universal-policy] - política universal já estava aplicada")
elif old in s:
    s = s.replace(old, new, 1)
    sources.write_text(s, encoding="utf-8")
    print("OK [universal-policy] - referência operacional generalizada para qualquer fonte")
else:
    raise SystemExit(
        "ERRO [universal-reference]: não foi possível reconhecer o estado atual do bloco de referências"
    )

print("OK [universal-policy] - loading por toggle aplicado genericamente às camadas com id")
print("OK [universal-policy] - vetores adicionais independentes de tamanho e órgão")
print("POLÍTICA UNIVERSAL DE CAMADAS CONCLUÍDA")
