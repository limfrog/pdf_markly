// PDF Markly Service Worker
const CACHE_NAME = 'pdf-markly-v1';

// 오프라인에서도 동작할 핵심 파일들
const CORE_ASSETS = [
  './',
  './index.html',
];

// 외부 CDN 리소스 (캐시 가능한 것들)
const CDN_ASSETS = [
  'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/legacy/build/pdf.min.js',
  'https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/legacy/build/pdf.worker.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/pdf-lib/1.17.1/pdf-lib.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js',
];

// 설치: 핵심 파일 캐시
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      // 코어 파일 캐시
      await cache.addAll(CORE_ASSETS).catch(() => {});
      // CDN 파일은 개별로 시도 (실패해도 설치 계속)
      for (const url of CDN_ASSETS) {
        await cache.add(url).catch(() => {});
      }
    })
  );
  self.skipWaiting();
});

// 활성화: 오래된 캐시 삭제
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// 요청 가로채기: Cache First → Network Fallback
self.addEventListener('fetch', (event) => {
  // POST, non-GET 요청은 패스
  if (event.request.method !== 'GET') return;
  // chrome-extension 등 무시
  if (!event.request.url.startsWith('http')) return;

  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;

      // 캐시 없으면 네트워크 요청 후 캐시 저장
      return fetch(event.request)
        .then((response) => {
          if (!response || response.status !== 200 || response.type === 'opaque') {
            return response;
          }
          const toCache = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, toCache);
          });
          return response;
        })
        .catch(() => {
          // 오프라인 + 캐시 없음 → 빈 응답
          return new Response('오프라인 상태입니다.', {
            status: 503,
            headers: { 'Content-Type': 'text/plain; charset=utf-8' },
          });
        });
    })
  );
});
