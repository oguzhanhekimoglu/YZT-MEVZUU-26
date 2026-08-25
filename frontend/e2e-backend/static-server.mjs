import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const root = join(process.cwd(), "dist");
const contentTypes = { ".css": "text/css", ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml" };

createServer((request, response) => {
  const pathname = new URL(request.url ?? "/", "http://127.0.0.1").pathname;
  if (pathname === "/") { response.writeHead(302, { location: "/goruntule/" }); response.end(); return; }
  if (!pathname.startsWith("/goruntule/")) { response.writeHead(404); response.end(); return; }
  const relative = decodeURIComponent(pathname.slice("/goruntule/".length)) || "index.html";
  const file = normalize(join(root, relative));
  if (!file.startsWith(normalize(root)) || !existsSync(file) || !statSync(file).isFile()) { response.writeHead(404); response.end(); return; }
  response.writeHead(200, { "content-type": contentTypes[extname(file)] ?? "application/octet-stream", "cache-control": "no-store" });
  createReadStream(file).pipe(response);
}).listen(4173, "127.0.0.1");
