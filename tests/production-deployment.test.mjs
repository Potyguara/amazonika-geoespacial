import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const read = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("produção não publica PostGIS e vincula web/API ao localhost", async () => {
  const compose = await read("docker-compose.production.yml");
  assert.doesNotMatch(compose, /5432:5432/);
  assert.match(compose, /127\.0\.0\.1:18000:8000/);
  assert.match(compose, /127\.0\.0\.1:13000:3000/);
  assert.match(compose, /mem_limit: 3g/);
  assert.match(compose, /geo_private:\n\s+internal: true/);
});

test("proxy do Geoespacial é separado do SIS Amazonika", async () => {
  const nginx = await read("deploy/nginx/amazonika-geoespacial.conf");
  assert.match(nginx, /server_name geo\.amazonikaengenharia\.com\.br/);
  assert.match(nginx, /proxy_pass http:\/\/127\.0\.0\.1:18000/);
  assert.match(nginx, /proxy_pass http:\/\/127\.0\.0\.1:13000/);
  assert.doesNotMatch(nginx, /3333/);
});

test("API expõe readiness com consulta ao PostGIS", async () => {
  const main = await read("backend/app/main.py");
  assert.match(main, /@app\.get\("\/ready"/);
  assert.match(main, /SELECT 1/);
  assert.match(main, /status_code=503/);
});
