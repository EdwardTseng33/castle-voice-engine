const puppeteer = require('C:/Users/Administrator/.claude/skills/deck-screenshot-automation/node_modules/puppeteer-core');
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const BASE='https://edwardt0303--castle-voice-engine-fastapi-app.modal.run';
const URL=BASE+'/static/index.html?_cb=p404'+Date.now();
(async()=>{
  const b=await puppeteer.launch({executablePath:CHROME,headless:'new',args:['--no-sandbox','--autoplay-policy=no-user-gesture-required','--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']});
  const p=await b.newPage();
  const failed=[];
  p.on('response',r=>{ if(r.status()>=400) failed.push({url:r.url(),status:r.status()}); });
  await p.goto(URL,{waitUntil:'networkidle2',timeout:90000});
  await new Promise(r=>setTimeout(r,5000));
  await b.close();
  console.log(JSON.stringify(failed,null,2));
})().catch(e=>{console.error(e);process.exit(1);});
