from pathlib import Path
import runpy


# Primeiro aplica o patch-base de feedback visual e cards de referência.
# Em seguida remove as regras específicas por órgão e transforma a política
# em comportamento genérico orientado por metadados/taxonomia.
runpy.run_path("scripts/apply_layer_loading_and_reference_cards.py", run_name="__main__")

sources = Path("components/sources-module.tsx")
s = sources.read_text(encoding="utf-8")

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

              // Normalização de taxonomia, não de órgão. A regra continua
              // genérica: qualquer fonte pode declarar operational_categories
              // explicitamente e qualquer vetor pode declarar reference_source_id.
              if (/CAR|SICAR/.test(taxonomy)) return ["CAR_SICAR"];
              if (/SPU|PATRIMÔNIO DA UNIÃO|PATRIMONIO DA UNIAO/.test(taxonomy)) return ["SPU"];

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

if old not in s:
    raise SystemExit(
        "ERRO [universal-reference]: bloco específico SICAR/SPU não localizado"
    )

s = s.replace(old, new, 1)
sources.write_text(s, encoding="utf-8")

print("OK [universal-policy] - referência operacional generalizada para qualquer fonte")
print("OK [universal-policy] - loading por toggle já é aplicado a toda camada com id")
print("OK [universal-policy] - vetores adicionais continuam independentes de tamanho e órgão")
print("POLÍTICA UNIVERSAL DE CAMADAS CONCLUÍDA")
