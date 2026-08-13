/*
  Service worker do Bola na Rede.

  É o que faz o app funcionar sem internet. O técnico usa na quadra do Centro
  de Cultura e Esporte, onde o sinal cai direto, então precisava abrir mesmo
  offline em vez de dar tela de dinossauro.

  A estratégia é: tenta a rede primeiro (pra sempre mostrar dado atualizado) e,
  se não conseguir, usa o que ficou guardado da última visita.
*/

const CACHE = "bola-na-rede-v1";

// O básico pra tela abrir mesmo sem rede na primeira vez.
const ARQUIVOS_BASE = [
  "/",
  "/offline",
  "/static/estilo.css",
  "/static/icone.svg",
  "/static/icone-192.png",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches
      .open(CACHE)
      // addAll falha inteiro se um arquivo só der erro, então guardo um por um.
      .then((cache) => Promise.allSettled(ARQUIVOS_BASE.map((a) => cache.add(a))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((nomes) =>
        Promise.all(nomes.filter((n) => n !== CACHE).map((n) => caches.delete(n)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (evento) => {
  const req = evento.request;

  // Só mexo com GET. POST (salvar chamada, convocação) tem que ir pra rede
  // de verdade, senão o técnico acha que salvou e não salvou.
  if (req.method !== "GET") return;

  // Nem tento guardar coisa de outro site.
  if (new URL(req.url).origin !== self.location.origin) return;

  evento.respondWith(
    fetch(req)
      .then((resposta) => {
        // Deu certo: guardo uma cópia pra próxima vez que faltar internet.
        const copia = resposta.clone();
        caches.open(CACHE).then((cache) => cache.put(req, copia));
        return resposta;
      })
      .catch(() =>
        caches.match(req).then((guardado) => {
          if (guardado) return guardado;
          // Se for navegação de página e não tem nada guardado, mostro a
          // tela de offline em vez do erro do navegador.
          if (req.mode === "navigate") return caches.match("/offline");
          return Response.error();
        })
      )
  );
});
