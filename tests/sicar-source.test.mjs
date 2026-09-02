import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("SICAR usa WMS oficial e vetor WFS sob demanda", () => {
  const config = readFileSync("backend/app/configure_official_sources.py", "utf8");
  const analyzer = readFileSync("backend/app/services/analyzer.py", "utf8");
  assert.match(config, /sicar-imoveis-rurais/);
  assert.match(config, /geoserver\.car\.gov\.br\/geoserver\/sicar\/wms/);
  assert.match(config, /"wfs_on_demand": True/);
  assert.match(analyzer, /sync_sicar_wfs_bbox/);
});

test("gerenciador de camadas possui rolagem interna", () => {
  const css = readFileSync("app/globals.css", "utf8");
  assert.match(css, /\.layer-manager-list[\s\S]*overflow-y: auto/);
  assert.match(css, /\.layer-manager-sheet[\s\S]*height: 100dvh/);
});
