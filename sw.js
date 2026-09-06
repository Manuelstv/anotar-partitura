// SERVICE WORKER — e o que transforma o site em app instalavel e offline.
//
// O que pesa aqui NAO sao os arquivos do projeto (0,3 MB somados), e sim o Pyodide com o
// PyMuPDF: 21,6 MB baixados do CDN, medidos numa leitura de PDF. Sem cache isso vem a
// CADA visita, e e o motivo de demorar no celular. Com cache, vem uma vez.
//
// Duas politicas, e a diferenca importa:
//   - o HTML e a rede PRIMEIRO: senao uma versao nova nunca chega ao aparelho de quem ja
//     instalou, e o app congela na versao do dia da instalacao;
//   - o resto e o cache PRIMEIRO, porque toda URL ja carrega versao (o `?v=` do site e o
//     numero da versao no caminho do Pyodide). URL versionada nao muda de conteudo.
const VERSAO = "v54";
const CACHE = "partitura-" + VERSAO;
const CDN = "https://cdn.jsdelivr.net/pyodide/";

// so o esqueleto entra na instalacao. O Pyodide NAO e pre-cacheado de proposito: sao
// 21 MB, e quem so quer ver a pagina nao deve pagar por eles antes de mandar um arquivo.
const ESQUELETO = [
  "./",
  "./index.html",
  "./sax.js",
  "./manifest.webmanifest",
  "./icone-180.png",
  "./icone-192.png",
  "./icone-512.png",
];

self.addEventListener("install", (ev) => {
  ev.waitUntil((async () => {
    const c = await caches.open(CACHE);
    // addAll falha inteiro se UM arquivo falhar; aqui um icone ausente nao pode
    // impedir a instalacao do app
    await Promise.allSettled(ESQUELETO.map((u) => c.add(u)));
    self.skipWaiting();
  })());
});

self.addEventListener("activate", (ev) => {
  ev.waitUntil((async () => {
    const nomes = await caches.keys();
    await Promise.all(nomes.filter((n) => n !== CACHE).map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (ev) => {
  const req = ev.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const meu = url.origin === self.location.origin;
  const doPyodide = req.url.startsWith(CDN);
  if (!meu && !doPyodide) return;           // qualquer outra origem passa direto

  // o documento vem da rede primeiro, com o cache como rede de seguranca
  const eDocumento = req.mode === "navigate" ||
                     (meu && url.pathname.endsWith(".html"));
  if (eDocumento) {
    ev.respondWith((async () => {
      try {
        const r = await fetch(req);
        const c = await caches.open(CACHE);
        c.put(req, r.clone());
        return r;
      } catch (e) {
        return (await caches.match(req)) ||
               (await caches.match("./index.html")) ||
               Response.error();
      }
    })());
    return;
  }

  ev.respondWith((async () => {
    const achado = await caches.match(req, { ignoreVary: true });
    if (achado) return achado;
    const r = await fetch(req);
    // `opaque` e resposta de outra origem sem CORS: nao da para saber se deu certo, e
    // guardar isso envenena o cache com erro disfarcado de sucesso
    if (r && (r.ok || r.type === "opaque") && r.type !== "opaque") {
      const c = await caches.open(CACHE);
      c.put(req, r.clone());
    }
    return r;
  })());
});
