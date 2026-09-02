import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("análise transforma SIRGAS 2000 para geography 4326 e remove Z", async () => {
  const source = await readFile(
    new URL("../backend/app/services/analyzer.py", import.meta.url),
    "utf8",
  );
  assert.match(source, /force_2d\(shape\(geometry\)\)/);
  assert.match(source, /ST_Transform\(geometry,4326\)/);
  assert.match(source, /Geography\(geometry_type="GEOMETRY",srid=4326\)/);
  assert.doesNotMatch(source, /func\.cast\(db_geom, Geography\)/);
});

test("análise usa vizinho KNN e limite por fonte sem varredura geográfica global", async () => {
  const source = await readFile(
    new URL("../backend/app/services/analyzer.py", import.meta.url),
    "utf8",
  );
  assert.match(source, /GeoFeature\.geom\.op\("<->"\)/);
  assert.match(source, /statement_timeout = '20s'/);
  assert.match(source, /with db\.begin_nested\(\)/);
  assert.doesNotMatch(source, /func\.min\(func\.ST_Distance/);
});
