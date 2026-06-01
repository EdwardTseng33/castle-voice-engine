const puppeteer = require('C:/Users/Administrator/.claude/skills/deck-screenshot-automation/node_modules/puppeteer-core');
const fs = require('fs');
const path = require('path');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const BASE = 'https://edwardt0303--castle-voice-engine-fastapi-app.modal.run'; // PROD
const URL = BASE + '/static/index.html?_cb=prodlive' + Date.now();
const OUT = 'C:/Users/Administrator/Documents/Codex/2026-06-01/ai/work/castle-voice-engine-live/_verify';
const sleep = ms => new Promise(r=>setTimeout(r,ms));

(async () => {
  const result = { env:'PROD', url: URL, ts: new Date().toISOString(), checks: {}, consoleErrors: [], pageErrors: [] };

  // ---- A. backend director endpoints (情緒腦) ----
  const statusResp = await fetch(BASE + '/director/status');
  result.checks.director_status_code = statusResp.status;
  const statusJson = await statusResp.json().catch(()=>null);
  result.checks.director_status_ok = !!(statusJson && statusJson.ok);
  result.checks.director_states = statusJson ? statusJson.states : null;

  const decA = await fetch(BASE+'/director/decide',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({transcript:'我今天好累'})});
  const decAj = await decA.json().catch(()=>null);
  result.checks.decide_tired = decAj ? {state:decAj.state, lane:decAj.realtime&&decAj.realtime.lane, preamble:decAj.realtime&&decAj.realtime.preamble} : {http:decA.status};

  const decB = await fetch(BASE+'/director/decide',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({transcript:'幫我規劃工作',requested_mode:'work'})});
  const decBj = await decB.json().catch(()=>null);
  result.checks.decide_work = decBj ? {state:decBj.state, lane:decBj.realtime&&decBj.realtime.lane, call_claude:decBj.claude&&decBj.claude.should_call} : {http:decB.status};

  // ---- B. real browser (visible) ----
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox','--disable-setuid-sandbox','--autoplay-policy=no-user-gesture-required',
      '--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--window-size=1280,860'],
    defaultViewport: { width: 1280, height: 800 }
  });
  const page = await browser.newPage();
  page.on('console', m => { if (m.type()==='error') result.consoleErrors.push(m.text().slice(0,300)); });
  page.on('pageerror', e => result.pageErrors.push(String(e).slice(0,300)));

  const resp = await page.goto(URL, { waitUntil: 'networkidle2', timeout: 90000 });
  result.checks.httpStatus = resp ? resp.status() : null;
  await sleep(4000);

  const html = await page.content();
  const vmatch = html.match(/2\.0\.\d+[\w.-]*/);
  result.checks.versionStringFound = vmatch ? vmatch[0] : null;

  // 情緒層 markers
  result.checks.emotionLayer_liveVideoEmotion = !!(await page.$('#liveVideoEmotion'));
  result.checks.preCallFn = await page.evaluate(() => typeof window.__sophiePlayEmotionPreCall === 'function');
  result.checks.visionToEmotionFn = await page.evaluate(() => typeof window.__sophieVisionToEmotion === 'function');

  // 影片真播 (visible env)
  const vid = await page.evaluate(async () => {
    const vs = Array.from(document.querySelectorAll('video'));
    const t0 = Date.now();
    while (Date.now()-t0 < 15000) {
      if (vs.some(v => v.readyState >= 3)) break;
      await new Promise(r=>setTimeout(r,500));
    }
    return vs.map(v => ({ id:v.id||v.className, readyState:v.readyState, paused:v.paused,
      currentTime:+v.currentTime.toFixed(2), visible: v.offsetParent!==null,
      src:(v.currentSrc||v.src||'').split('/').pop() }));
  });
  result.checks.videos = vid;
  result.checks.anyVideoReady = vid.some(v => v.readyState >= 3);

  // currentTime 推進確認 (真播 not 靜止幀)
  const ct1 = await page.evaluate(()=>{var v=document.querySelector('video');return v?+v.currentTime.toFixed(3):null;});
  await sleep(2000);
  const ct2 = await page.evaluate(()=>{var v=document.querySelector('video');return v?+v.currentTime.toFixed(3):null;});
  result.checks.idle_video_advancing = (ct2!==null && ct1!==null && ct2 > ct1);
  result.checks.ct_samples = [ct1, ct2];

  // 情緒淡入層不閃 (opacity 取樣 6x)
  const opacitySamples = await page.evaluate(async () => {
    const el = document.querySelector('#liveVideoEmotion');
    if (!el) return null;
    const s = [];
    for (let i=0;i<6;i++){ s.push(parseFloat(getComputedStyle(el).opacity)); await new Promise(r=>setTimeout(r,500)); }
    return s;
  });
  result.checks.emotionOpacitySamples = opacitySamples;
  // 不閃判定: 沒有相鄰兩次 0<->1 劇烈跳動
  if (opacitySamples) {
    let thrash=0;
    for (let i=1;i<opacitySamples.length;i++){ if (Math.abs(opacitySamples[i]-opacitySamples[i-1])>0.5) thrash++; }
    result.checks.emotion_no_flicker = thrash <= 1;
  }

  await page.screenshot({ path: path.join(OUT,'prod_desktop.png') });
  result.checks.screenshot_desktop = 'prod_desktop.png';

  await browser.close();

  result.consoleErrorCount = result.consoleErrors.length;
  result.pageErrorCount = result.pageErrors.length;
  fs.writeFileSync(path.join(OUT,'prod_result.json'), JSON.stringify(result,null,2));
  console.log(JSON.stringify(result,null,2));
})().catch(e => { console.error('HARNESS ERROR', e); process.exit(1); });
