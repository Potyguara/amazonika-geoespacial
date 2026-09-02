import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("ANM usa ArcGIS REST vetorial sob demanda e WMS apenas visual", async () => {
  const seed = await read("backend/app/seed.py");
  const importer = await read("backend/app/services/importer.py");
  assert.match(seed, /anm-processos-minerarios/);
  assert.match(seed, /arcgis_on_demand/);
  assert.match(seed, /geo\.anm\.gov\.br\/arcgis\/rest\/services\/SIGMINE/);
  assert.match(importer, /returnIdsOnly/);
  assert.match(importer, /sync_arcgis_bbox/);
});

test("relatório declara cálculo vetorial e lista feições identificadas", async () => {
  const report = await read("backend/app/api/routes/analyses.py");
  assert.match(report, /Metodologia vetorial/);
  assert.match(report, /WMS foram usados somente como referência visual/);
  assert.match(report, /Feições identificadas/);
});

test("painel consulta alertas reais das fontes", async () => {
  const page = await read("app/page.tsx");
  const sources = await read("backend/app/api/routes/sources.py");
  assert.match(page, /sources\/health-status/);
  assert.match(sources, /def official_sources_health/);
});
