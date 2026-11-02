import assert from "node:assert/strict";
import test from "node:test";

const developmentPreviewMeta =
  /<meta(?=[^>]*\bname=["']codex-preview["'])(?=[^>]*\bcontent=["']development["'])[^>]*>/i;

test("renders development preview metadata", async () => {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: entry } = await import(workerUrl.href);

  // A saída Node do Vinext (App Router/RSC) exporta um handler diretamente.
  // Builds em formato Worker podem exportar um objeto com fetch().
  // Ambos precisam renderizar HTML real; não substituímos o teste por um mock.
  const handleRequest =
    typeof entry === "function" ? entry : entry?.fetch?.bind(entry);

  assert.equal(
    typeof handleRequest,
    "function",
    "A entrada gerada pelo Vinext deve exportar um handler HTTP válido",
  );

  const response = await handleRequest(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );

  assert.equal(response.status, 200);
  assert.match(
    response.headers.get("content-type") ?? "",
    /^text\/html\b/i,
  );
  assert.match(await response.text(), developmentPreviewMeta);
});
