/* GEO-83B - Proxy local de homologação; nenhum destino externo. */
"use strict";
const http = require("node:http");
const targets = {
  api: { hostname: "amazonika-geo83-api", port: 8000 },
  web: { hostname: "amazonika-geo83-web", port: 3000 },
};
const server = http.createServer((req, res) => {
  const url = req.url || "/";
  const type = url === "/api" || url.startsWith("/api/") ? "api" : "web";
  const target = targets[type];
  const headers = { ...req.headers, host: target.hostname + ":" + target.port };
  const upstream = http.request({
    hostname: target.hostname, port: target.port,
    path: url, method: req.method, headers,
    timeout: 30000,
  }, (response) => {
    res.writeHead(response.statusCode || 502, response.headers);
    response.pipe(res);
  });
  upstream.on("timeout", () => upstream.destroy(new Error("upstream timeout")));
  upstream.on("error", (err) => {
    console.error(type, err.message);
    if (!res.headersSent) res.writeHead(502, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("GEO83: serviço temporário indisponível");
  });
  req.pipe(upstream);
});
server.listen(8080, "0.0.0.0", () => console.log("GEO83 proxy interno em 8080"));
