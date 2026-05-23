// castle/static/sw.js
// Voice Path v1.1.2.1 Service Worker
// 待機 shell offline-first · realtime / breeze / musetalk 永遠 network-first 不 cache
// v1.1.0 baseline · push notification handler + background sync handler (framework only · server 端 push 尚未 build)
const CACHE_VERSION = 'v1.9.11';
const CACHE_NAME = 'sophie-' + CACHE_VERSION;

// 不 precache mp4 (5MB+ · 阻塞 install) · video element 自己 streaming load 即可
const SHELL_ASSETS = [
  '/static/index.html',
  '/static/animation-pool.js',
  '/static/session-memory.js',
  '/static/conversation-memory.js',  // v1.1.2 · IndexedDB 7 day raw / 30 day summary
  '/static/phrase-matcher.js',       // v1.5.0 · 嘴對齊 fuzzy match
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

// v1.9.10 · 收到 SKIP_WAITING 訊息立刻啟用新版 (讓 page reload 拿到新 SW)
self.addEventListener('message', function (event) {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
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

  // v1.9.5 · index.html = network-first 強制 (避免 Edward 看到 cache 舊版含 poster)
  if (url.pathname === '/static/index.html') {
    event.respondWith(
      fetch(event.request).then(function (resp) {
        if (resp && resp.ok) {
          var clone = resp.clone();
          caches.open(CACHE_NAME).then(function (c) { c.put(event.request, clone); });
        }
        return resp;
      }).catch(function () {
        return caches.match(event.request);
      })
    );
    return;
  }

  // 其他 shell asset = stale-while-revalidate
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

// v1.1.0 · push notification baseline (server push 待 v1.2+ build · 現在只是接收框架)
self.addEventListener('push', function (event) {
  var title = '蘇菲';
  var body = '蘇菲找你';
  var data = {};
  if (event.data) {
    try {
      var payload = event.data.json();
      title = payload.title || title;
      body = payload.body || body;
      data = payload.data || {};
    } catch (e) {
      body = event.data.text() || body;
    }
  }
  event.waitUntil(
    self.registration.showNotification(title, {
      body: body,
      icon: '/static/icon-192.png',
      badge: '/static/icon-192.png',
      tag: 'sophie-push',
      renotify: true,
      data: data
    })
  );
});

// 點 notification → focus 蘇菲 tab (或開新 tab)
self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  var targetUrl = (event.notification.data && event.notification.data.url) || '/static/index.html';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (winList) {
      for (var i = 0; i < winList.length; i++) {
        var client = winList[i];
        if (client.url.indexOf('/static/') !== -1 && 'focus' in client) {
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});

// v1.1.0 · background sync baseline (server queue 待 v1.2+ build · 現在只是接收框架)
self.addEventListener('sync', function (event) {
  if (event.tag === 'sophie-pending-messages') {
    event.waitUntil(
      // 未來：fetch /messages/pending → 顯示通知
      // baseline · 純 framework · 不做事
      Promise.resolve()
    );
  }
});
