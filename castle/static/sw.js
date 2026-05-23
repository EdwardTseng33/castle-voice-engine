// castle/static/sw.js
// Voice Path v0.7 Service Worker
// 待機 shell offline-first · realtime / breeze / musetalk 永遠 network-first 不 cache
const CACHE_VERSION = 'v0.9.3';
const CACHE_NAME = 'sophie-' + CACHE_VERSION;

// 不 precache mp4 (5MB+ · 阻塞 install) · video element 自己 streaming load 即可
const SHELL_ASSETS = [
  '/static/index.html',
  '/static/animation-pool.js',
  '/static/manifest.json'
];

// 任何 realtime / lipsync / ASR / health endpoint 都絕不 cache
const NEVER_CACHE = [
  '/sdp',
  '/voice/',
  '/musetalk/',
  '/realtime/',
  '/breeze/',
  '/health',
  '/session/'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(SHELL_ASSETS).catch(function (err) {
        console.warn('[sw] precache partial:', err);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k.indexOf('sophie-') === 0 && k !== CACHE_NAME; })
            .map(function (k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function (event) {
  var url = new URL(event.request.url);

  // CRITICAL · video / audio 完全 bypass SW · 讓瀏覽器 native fetch 處理 Range request
  // SW respondWith fetch() 會把 206 partial 變 200 全檔、video element 不能 streaming play
  if (url.pathname.endsWith('.mp4') || url.pathname.endsWith('.webm') ||
      url.pathname.endsWith('.m4a') || url.pathname.endsWith('.ogg')) {
    return; // 不 respondWith = SW pass-through
  }

  // realtime / lipsync / ASR 路徑 = 永遠 network · 不 cache
  for (var i = 0; i < NEVER_CACHE.length; i++) {
    if (url.pathname.indexOf(NEVER_CACHE[i]) === 0) {
      event.respondWith(fetch(event.request));
      return;
    }
  }

  // shell asset = stale-while-revalidate
  if (event.request.method === 'GET' && SHELL_ASSETS.indexOf(url.pathname) !== -1) {
    event.respondWith(
      caches.match(event.request).then(function (cached) {
        var fetchPromise = fetch(event.request).then(function (resp) {
          if (resp && resp.ok) {
            var clone = resp.clone();
            caches.open(CACHE_NAME).then(function (c) { c.put(event.request, clone); });
          }
          return resp;
        }).catch(function () { return cached; });
        return cached || fetchPromise;
      })
    );
    return;
  }

  // 其餘 = network-first · fallback cache
  event.respondWith(
    fetch(event.request).catch(function () { return caches.match(event.request); })
  );
});
