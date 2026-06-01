
const puppeteer = require('C:/Users/Administrator/.claude/skills/deck-screenshot-automation/node_modules/puppeteer-core');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const FFMPEG = 'C:/Users/Administrator/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.1-full_build/bin/ffmpeg.exe';
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const URL = 'http://localhost:8753/static/index.html?diag=wake';
const OUTDIR = 'C:/Users/Administrator/Documents/Codex/2026-06-01/ai/work/castle-voice-engine-live/_verify';

function sleep(ms){return new Promise(r=>setTimeout(r,ms));}

async function record(page, label, durationMs, setup, during){
  const framesDir = path.join(OUTDIR, 'frames_'+label);
  fs.rmSync(framesDir,{recursive:true,force:true});
  fs.mkdirSync(framesDir,{recursive:true});
  const client = await page.target().createCDPSession();
  const frames=[];
  client.on('Page.screencastFrame', async (ev)=>{
    frames.push({data:ev.data, ts:ev.metadata.timestamp});
    try{ await client.send('Page.screencastFrameAck',{sessionId:ev.sessionId}); }catch(e){}
  });
  if(setup) await setup();
  await client.send('Page.startScreencast',{format:'jpeg',quality:80,everyNthFrame:1});
  if(during) await during(durationMs); else await sleep(durationMs);
  await sleep(200);
  await client.send('Page.stopScreencast');
  await sleep(300);
  let concat='';
  for(let i=0;i<frames.length;i++){
    const fn=path.join(framesDir, String(i).padStart(5,'0')+'.jpg');
    fs.writeFileSync(fn, Buffer.from(frames[i].data,'base64'));
    let dur = (i<frames.length-1) ? Math.max(0.02, frames[i+1].ts-frames[i].ts) : 0.1;
    concat += "file '"+fn.split(path.sep).join('/')+"'\n" + "duration "+dur.toFixed(3)+"\n";
  }
  if(frames.length){
    const lastfn=path.join(framesDir, String(frames.length-1).padStart(5,'0')+'.jpg').split(path.sep).join('/');
    concat += "file '"+lastfn+"'\n";
  }
  const listFile=path.join(framesDir,'list.txt');
  fs.writeFileSync(listFile, concat);
  const out=path.join(OUTDIR, 'sophie-'+label+'.mp4');
  execFileSync(FFMPEG, ['-y','-f','concat','-safe','0','-i',listFile,'-vsync','vfr','-pix_fmt','yuv420p','-movflags','+faststart', out], {stdio:'pipe'});
  fs.rmSync(framesDir,{recursive:true,force:true});
  console.log('['+label+'] frames='+frames.length+' -> '+out);
  return {out, frames:frames.length};
}

(async()=>{
  fs.mkdirSync(OUTDIR,{recursive:true});
  const browser=await puppeteer.launch({
    executablePath:CHROME, headless:'new',
    args:['--autoplay-policy=no-user-gesture-required','--mute-audio','--no-sandbox','--window-size=900,1100']
  });
  const page=await browser.newPage();
  await page.setViewport({width:900,height:1100,deviceScaleFactor:1});
  const logs=[];
  page.on('console', m=>{ const t=m.text(); if(/emotion|vision|director|precall|pre-call/i.test(t)) logs.push(t); });
  page.on('pageerror', e=>logs.push('PAGEERROR: '+e.message));
  await page.goto(URL,{waitUntil:'domcontentloaded',timeout:30000});
  await sleep(2500);
  await page.evaluate(()=>{
    const sel='[class*="modal"],[class*="overlay"],[class*="signin"],[class*="wake"]';
    document.querySelectorAll(sel).forEach(el=>{
      const cs=getComputedStyle(el);
      if(cs.position==='fixed'||cs.position==='absolute'||parseInt(cs.zIndex||'0')>10){ el.style.display='none'; }
    });
  });
  await sleep(500);

  await record(page,'taskA-precall', 11000, async()=>{
    await page.evaluate(()=>{
      window.__sophieInCall=false;
      if(window.__sophieStartPreCallEmotionPreview) window.__sophieStartPreCallEmotionPreview();
    });
  }, async(dur)=>{
    const picks=['stroke-hair','happy','greeting','acknowledgement'];
    const step=Math.floor(dur/(picks.length+1));
    for(let i=0;i<picks.length;i++){
      await sleep(step);
      await page.evaluate((p)=>{ if(window.__sophiePlayEmotionPreCall) window.__sophiePlayEmotionPreCall(p); }, picks[i]);
    }
    await sleep(step);
  });

  await page.evaluate(()=>{ if(window.__sophieStopPreCallEmotionPreview) window.__sophieStopPreCallEmotionPreview(); });
  await sleep(300);
  await record(page,'taskB-incall-vision', 12000, async()=>{
    await page.evaluate(()=>{ window.__sophieInCall=true; });
  }, async(dur)=>{
    const seq=[
      {label:'happy', src:'emotion'},
      {label:'apologetic', src:'emotion'},
      {label:'playful', src:'pose-hands'},
      {label:'greeting', src:'pose-hands'},
      {label:'resigned', src:'emotion'}
    ];
    const step=Math.floor(dur/(seq.length+1));
    for(let i=0;i<seq.length;i++){
      await sleep(step);
      await page.evaluate((o)=>{ if(window.__sophieVisionToEmotion) window.__sophieVisionToEmotion(o.label,o.src); }, seq[i]);
    }
    await sleep(step);
  });

  fs.writeFileSync(path.join(OUTDIR,'console.log'), logs.join('\n'),'utf8');
  console.log('--- relevant console lines ---');
  console.log(logs.join('\n'));
  await browser.close();
})().catch(e=>{ console.error('HARNESS FAIL:', e); process.exit(1); });
