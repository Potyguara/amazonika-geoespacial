import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (relative) => readFile(new URL(`../${relative}`, import.meta.url), "utf8");

test("peças técnicas mantêm perfil profissional isolado do cadastro principal", async () => {
  const api = await read("backend/app/api/routes/tools.py");
  const map = await read("components/geo-map.tsx");
  assert.match(api, /class ProfessionalDocumentOverride\(BaseModel\)/);
  assert.match(api, /_document_professional\(user, payload\)/);
  assert.match(map, /\/auth\/me\/professional-profile/);
  assert.match(map, /professional_override: documentProfessional/);
  assert.doesNotMatch(map, /method: "PUT"[^}]*\/auth\/me\/professional-profile/);
});

test("planta de situação tem captura própria e proporção fixa no PDF", async () => {
  const mini = await read("components/situation-map-preview.tsx");
  const pdf = await read("backend/app/services/plant_memorial_v3.py");
  assert.match(mini, /map\.getViewport\(\)/);
  assert.match(mini, /result\.toDataURL\("image\/jpeg"/);
  assert.match(mini, /geometry_key: geoKeyRef\.current/);
  assert.match(pdf, /frame_height=min\(available_raster_h,frame_width\*0\.75\)/);
  assert.match(pdf, /preserveAspectRatio=True,anchor="c"/);
});

test("opções avançadas são enviadas ao gerador e modificam os elementos", async () => {
  const ui = await read("components/pecas-tecnicas-workspace.tsx");
  const map = await read("components/geo-map.tsx");
  const api = await read("backend/app/api/routes/tools.py");
  const pdf = await read("backend/app/services/plant_memorial_v3.py");
  assert.match(ui, /PLANT_OPTIONS/);
  assert.match(ui, /onToggleElement\(key, event\.target\.checked\)/);
  assert.match(map, /plant_elements: plantElements/);
  assert.match(api, /class PlantElements\(BaseModel\)/);
  assert.match(pdf, /if enabled\("grid"\)/);
  assert.match(pdf, /if enabled\("coordinates"\)/);
  assert.match(pdf, /if not enabled\("vertex_labels"\)/);
});

test("pré-visualização usa blob real e invalida alterações de elementos e enquadramento", async () => {
  const ui = await read("components/pecas-tecnicas-workspace.tsx");
  assert.match(ui, /URL\.createObjectURL\(blob\)/);
  assert.match(ui, /rasterKey, elements, declination, situationKey, situationToken/);
  assert.match(ui, /lastPdfKey\.current === pdfKey/);
});
