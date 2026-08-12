const CACHE_NAME = 'pdf-markly-v2';
const CDN_CACHE = 'pdf-markly-cdn-v2';
const ASSETS = ['./', './index.html', './manifest.json',
  './favicon.png', './icon-192.png', './icon-512.png'];

// 오프라인에서도 동작해야 하는 CDN 라이브러리 (미리 캐싱 시도)
const CDN_ASSETS = [
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/pdf-lib/1.17.1/pdf-lib.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js'
];

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const c = await caches.open(CACHE_NAME);
    await c.addAll(ASSETS);
    // CDN은 개별적으로 캐싱 시도 — 하나 실패해도 설치는 계속
    const cdn = await caches.open(CDN_CACHE);
    await Promise.allSettled(
      CDN_ASSETS.map(async url => {
        try {
          const res = await fetch(url, { mode: 'cors', cache: 'no-cache' });
          if (res.ok || res.type === 'opaque') await cdn.put(url, res.clone());
        } catch (_) { /* 오프라인이면 최초 사용 시 캐싱됨 */ }
      })
    );
  })());
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME && k !== CDN_CACHE).map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // CDN 라이브러리: 캐시 우선 + 없으면 네트워크 후 저장
  if (url.hostname === 'cdnjs.cloudflare.com') {
    e.respondWith((async () => {
      const cdn = await caches.open(CDN_CACHE);
      const cached = await cdn.match(e.request);
      if (cached) return cached;
      try {
        const res = await fetch(e.request);
        if (res && (res.ok || res.type === 'opaque')) cdn.put(e.request, res.clone());
        return res;
      } catch (err) {
        return cached || Response.error();
      }
    })());
    return;
  }

  // 같은 출처가 아니면 그냥 통과
  if (url.origin !== self.location.origin) return;

  const isHTML = url.pathname.endsWith('.html') || url.pathname.endsWith('/');
  if (isHTML) {
    e.respondWith(
      fetch(e.request).then(res => {
        const clone = res.clone();
        caches.open(CACHE_NAME).then(c => c.put(e.request, clone));
        return res;
      }).catch(() => caches.match(e.request))
    );
  } else {
    e.respondWith(caches.match(e.request).then(cached => cached || fetch(e.request)));
  }
});

self.addEventListener('message', e => {
  if (e.data === 'skipWaiting') self.skipWaiting();
});
