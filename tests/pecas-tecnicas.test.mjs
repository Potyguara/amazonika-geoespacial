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
  assert.match(pdf, /frame_height = frame_width\*0\.75/);
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
  assert.match(pdf, /if enabled\("vertex_labels"\)/);
});

test("pré-visualização usa blob real e invalida alterações de elementos e enquadramento", async () => {
  const ui = await read("components/pecas-tecnicas-workspace.tsx");
  assert.match(ui, /URL\.createObjectURL\(blob\)/);
  assert.match(ui, /rasterKey, elements, declination, surveyDate, situationKey, situationToken/);
  assert.match(ui, /lastPdfKey\.current === pdfKey/);
});

test("peças técnicas persistem por usuário e podem ser reabertas", async () => {
  const routes = await read("backend/app/api/routes/technical_pieces.py");
  const model = await read("backend/app/models/technical_piece.py");
  const page = await read("app/page.tsx");
  const map = await read("components/geo-map.tsx");
  assert.match(routes, /TechnicalPiece.user_id == user.id/);
  assert.match(routes, /@router.post\(""/);
  assert.match(routes, /@router.put\("\/\{piece_id\}"/);
  assert.match(model, /__tablename__ = "technical_pieces"/);
  assert.match(page, /Peças Técnicas/);
  assert.match(page, /restorePiece=\{restorePiece\}/);
  assert.match(map, /setWorkspaceOpen\(true\)/);
});

test("memorial revisado é encaminhado para DOCX e PDF", async () => {
  const api = await read("backend/app/api/routes/tools.py");
  const docx = await read("backend/app/services/memorial_docx.py");
  const pdf = await read("backend/app/services/plant_memorial_v3.py");
  const map = await read("components/geo-map.tsx");
  assert.match(api, /edited_memorial: str \| None/);
  assert.match(docx, /edited_memorial: str \| None/);
  assert.match(pdf, /if edited_memorial is not None:/);
  assert.match(map, /edited_memorial: editedMemorial/);
});

test("mapa geoespacial permanece montado ao trocar de menu", async () => {
  const page = await read("app/page.tsx");
  assert.match(page, /display: activeView === "map" \? "contents" : "none"/);
  assert.match(page, /<TechnicalPiecesModule/);
});

test("quadro de assinaturas e azimutes compactos estão na prancha", async () => {
  const pdf = await read("backend/app/services/plant_memorial_v3.py");
  assert.match(pdf, /QUADRO DE ASSINATURAS/);
  assert.match(pdf, /PROPRIETÁRIO \/ DETENTOR/);
  assert.match(pdf, /RESPONSÁVEL TÉCNICO/);
  assert.match(pdf, /lines\.append\("Az\. "\+_azimuth_minutes/);
  assert.match(pdf, /lines\.append\("Dist\. "\+_br_number/);
});

test("memorial editado é gravado no backend pelo botão próprio", async () => {
  const workspace = await read("components/pecas-tecnicas-workspace.tsx");
  assert.match(workspace, /await onSavePiece\(editableMemorial\)/);
  assert.match(workspace, /onSaveMemorial\(editableMemorial\)/);
  assert.match(workspace, /memorialDirty \|\| memorialSaved/);
});

test("Google Satélite no enquadramento é somente visualização, sem captura PDF", async () => {
  const side = await read("components/situation-map-preview.tsx");
  assert.match(side, /google-tiles\/session/);
  assert.match(side, /google-tiles\/attribution/);
  assert.match(side, /basemap === "google"/);
  assert.match(side, /disabled=\{busy \|\| basemap === "google" \|\| !licenseConfirmed/);
});

test("escala usa faixa separada e orientação calcula norte geográfico", async () => {
  const pdf = await read("backend/app/services/plant_memorial_v3.py");
  assert.match(pdf, /map_bottom = 42 \+ table_h \+ 39/);
  assert.match(pdf, /footer_y = vy-25/);
  assert.match(pdf, /longitude,latitude=max\(all_vertices,key=lambda pt:pt\[1\]\)/);
  assert.match(pdf, /get_factors\(longitude,latitude\)\.meridian_convergence/);
  assert.match(pdf, /America\/Belem/);
  assert.match(pdf, /declination:\+\.3f/);
});

test("cálculo WMM2025 usa data de referência e vértice mais ao norte", async () => {
  const pdf = await read("backend/app/services/plant_memorial_v3.py");
  const api = await read("backend/app/api/routes/tools.py");
  const workspace = await read("components/pecas-tecnicas-workspace.tsx");
  assert.match(pdf, /GeoMag\(coefficients_file="wmm\/WMM_2025\.COF"\)/);
  assert.match(pdf, /glat=latitude,glon=longitude,alt=0,time=decimal_year/);
  assert.match(api, /survey_date/);
  assert.match(workspace, /type="date"/);
});

test("orientação compacta mantém altura útil da grade e reserva a área de rótulos", async () => {
  const pdf = await read("backend/app/services/plant_memorial_v3.py");
  assert.match(pdf, /rose_box=Box\(/);
  assert.match(pdf, /magnetic_box=Box\(/);
  assert.match(pdf, /label_layout\.reserved\.extend\(\[rose_box, magnetic_box\]\)/);
  assert.match(pdf, /map_top = h - 88/);
  assert.doesNotMatch(pdf, /band_bottom=h-161/);
});
