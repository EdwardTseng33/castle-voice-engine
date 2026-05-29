// castle/static/sw.js
// Voice Path v1.1.2.1 Service Worker
// 待機 shell offline-first · realtime / breeze / musetalk 永遠 network-first 不 cache
// v1.1.0 baseline · push notification handler + background sync handler (framework only · server 端 push 尚未 build)
// v2.0.31 (2026-05-29): Edward 5/29 catch 後卡西法掃出「SW sophie-v2.0.6 鎖舊版」·
//   CACHE_VERSION 從 v1 起沒動過、activate 不清舊 cache、用戶拿到 stale index.html/js。
//   bump 版本 → activate 清掉所有 sophie-* 舊 cache · 配 skipWaiting + clients.claim 強制換新。
// v2.0.35 (2026-05-29 · Step 0 交付層根治): 今天鬼打牆 50% = SW 餵舊版 code。
//   舊版 .js / index.html 是 network-first (成功後仍 cache.put + 失敗 fallback cache) →
//   慢網路 / 部署 propagate 空檔仍可能吃到 stale code。
//   改成「程式碼純 network-only · 完全不碰 cache」: index.html + 所有 .js 不寫不讀 cache。
//   只有圖片 / icon 這類靜態資產才走 cache (這些不會 stale 出 bug)。mp4 由 fetch bypass。
//   skipWaiting + clients.claim + controllerchange 自動 reload (非通話中) 保持不變。
const CACHE_VERSION = 'v2.0.35';
const CACHE_NAME = 'sophie-' + CACHE_VERSION;

// v2.0.35 · 程式碼 (.js / index.html / manifest) 一律不 precache · 純 network-only。
//   只留真正靜態、不會 stale 出 bug 的圖片資產走快取 (PWA 離線 icon 用)。
const SHELL_ASSETS = [
  '/static/icon-192.png',
  '/static/icon-512.png',
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

// v2.0.35 · 程式碼資產 = 純 network-only · 完全不碰 cache (杜絕 stale code 來源)。
//   index.html / 任何 .js 命中 → fetch 直送、不寫 cache、不讀 cache fallback。
function isCodeAsset(url) {
  return url.pathname === '/static/index.html' ||
         url.pathname === '/' ||
         url.pathname === '/static/' ||
         url.pathname.endsWith('.html') ||
         url.pathname.endsWith('.js');
}

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

  // v2.0.35 · 程式碼 (index.html / 所有 .js) = 純 network-only。
  //   不寫 cache、不讀 cache fallback → 永遠拿 server 最新版、杜絕 stale code。
  //   離線時拿不到 = 直接 fail (程式碼不該離線用 · 待機 shell 由圖片資產 + video 自身撐)。
  if (isCodeAsset(url)) {
    event.respondWith(fetch(event.request));
    return;
  }

  // 其他 shell asset (圖片 / icon) = stale-while-revalidate (這些不會 stale 出 bug)
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
      Promise.resolve()
    );
  }
});
