// Execute packaged HTML in an emulated DOM. This is not a visual browser test.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {Demo} from '../public/demo.js';
import {createRequire} from 'node:module';
import {webcrypto,createHash,createHmac} from 'node:crypto';
const {parseHTML}=createRequire(import.meta.url)('linkedom');
const root=new URL('../',import.meta.url);
const lovePrice=JSON.parse(fs.readFileSync(new URL('public/catalog.json',root),'utf8')).cases.find(c=>c.id==='love').price;
const html=fs.readFileSync(new URL('index.html',root),'utf8');
async function until(condition){for(let i=0;i<1600;i++){if(await condition())return;await new Promise(r=>setTimeout(r,5));}throw Error('UI did not reach the expected state');}
function memory(){const data=new Map();return {getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),data};}

async function launch({portable=true,url='file:///Downloads/index.html',storage=memory(),insecure=false,blockedStorage=false,fetcher=null,telegram=null,motion=false,seeded=true}={}){
  if(seeded&&!blockedStorage&&!fetcher&&!url.startsWith('https:')&&!storage.getItem('clezzy-gifts-device-demo-v1')){
    const c=JSON.parse(fs.readFileSync(new URL('public/catalog.json',root),'utf8'));
    const d=new Demo(c,storage);d.data.stars=150000;d.data.grams=2500000;
    for(const id of ['rose','toybear','scaredcat'])d.addGift(id);d.save();
  }
  const source=portable?html:fs.readFileSync(new URL('public/index.html',root),'utf8');
  const {document,Event}=parseHTML(source);Object.defineProperty(document,'baseURI',{value:url});
  const registry=new Map(),requests=[],animationCalls=[];
  document.modelContext={registerTool:t=>registry.set(t.name,t)};
  const dialog=document.querySelector('#modal');
  Object.defineProperty(dialog,'open',{get:()=>dialog.hasAttribute('open')});
  dialog.showModal=()=>{dialog.setAttribute('open','');dialog.dataset.mode='modal';};dialog.show=()=>{dialog.setAttribute('open','');dialog.dataset.mode='nonmodal';};dialog.close=()=>dialog.removeAttribute('open');
  dialog.getBoundingClientRect=()=>({left:0,top:0,right:360,bottom:700});
  document.execCommand=()=>true;
  const where=new URL(url),location={href:url,origin:where.origin,protocol:where.protocol,search:where.search,hash:where.hash,reload(){}};
  const timers=new Set();
  const ctx={atob:s=>Buffer.from(s,'base64').toString('binary'),document,console,location,URL,URLSearchParams,TextEncoder,TextDecoder,AbortController,
    crypto:insecure?{getRandomValues:webcrypto.getRandomValues.bind(webcrypto)}:webcrypto,
    structuredClone:insecure?undefined:structuredClone,
    localStorage:storage,sessionStorage:memory(),navigator:{},
    history:{replaceState:(_a,_b,hash)=>{location.hash=hash;}},
    matchMedia:()=>({matches:!motion}),scrollTo(){},addEventListener(){},
    setInterval:()=>0,clearInterval(){},
    setTimeout(fn,ms){const timer=setTimeout(()=>{timers.delete(timer);fn();},ms===12000?12000:Math.min(ms,25));timers.add(timer);return timer;},
    clearTimeout(timer){clearTimeout(timer);timers.delete(timer);},
    fetch:async(path,options)=>{requests.push(String(path));return fetcher?fetcher(String(path),options):{ok:false,status:404,headers:{get:()=> 'text/html'}};},
    lottie:{loadAnimation(options){animationCalls.push(options);return {destroy(){},play(){},pause(){},addEventListener(name,fn){if(name==='DOMLoaded')fn();}};}}
  };
  if(telegram)ctx.Telegram={WebApp:telegram};
  if(blockedStorage)Object.defineProperty(ctx,'localStorage',{get(){throw Error('Storage blocked');}});
  ctx.window=ctx;vm.createContext(ctx);
  const append=document.head.append.bind(document.head);document.head.append=(node)=>{append(node);if(node.tagName==='SCRIPT'&&node.src?.includes('/assets/')){const rel=node.src.slice(node.src.indexOf('/assets/'));try{vm.runInContext(fs.readFileSync(new URL('dist'+decodeURIComponent(rel),root),'utf8'),ctx);node.onload?.();}catch(error){node.onerror?.(error);}}};
  for(const script of document.querySelectorAll('script')){
    const component=script.getAttribute('data-component')||script.getAttribute('src')?.replace(/^\.\//,'');
    const text=script.getAttribute('src')?fs.readFileSync(new URL('public/'+component,root),'utf8'):script.textContent;
    new vm.Script(text,{filename:component||'inline.js'});
    if(component==='assets/lottie.min.js')continue;
    vm.runInContext(text,ctx,{filename:component||'inline.js'});
  }
  await until(()=>ctx.ClezzyReady||document.querySelector('#reload-app'));
  const click=async selector=>{const node=document.querySelector(selector);assert.ok(node,'Missing button '+selector);node.dispatchEvent(new Event('click',{bubbles:true}));await new Promise(r=>setTimeout(r,10));};
  const value=el=>el.tagName==='SELECT'?(el.querySelector('option[selected]')||el.querySelector('option'))?.value:el.value;
  ctx.FormData=class {constructor(form){this.fields=[...form.querySelectorAll('[name]')].map(el=>[el.name||el.getAttribute('name'),value(el)]);}[Symbol.iterator](){return this.fields[Symbol.iterator]();}};
  const submit=async(selector,fields)=>{
    const form=document.querySelector(selector);assert.ok(form);
    for(const [name,value] of Object.entries(fields)){
      const input=form.querySelector(`[name="${name}"]`);assert.ok(input,name);
      if(input.tagName==='SELECT'){for(const option of input.querySelectorAll('option')){if(option.value===value)option.setAttribute('selected','');else option.removeAttribute('selected');}}else input.value=value;
    }
    form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setTimeout(r,15));
  };
  return {ctx,document,Event,registry,requests,animationCalls,storage,click,submit,read:()=>registry.get('read_gift_inventory').execute({}),close:()=>{for(const timer of timers)clearTimeout(timer);}};
}

test('standalone HTML boots offline with all images embedded',async()=>{
  const page=await launch();try{
    assert.ok(page.ctx.ClezzyReady);assert.equal(page.requests.length,0);
    assert.match(page.document.querySelector('title').textContent,/OtonGifts/);
    assert.equal(page.document.querySelectorAll('.game-poster').length,4);
    assert.ok(page.document.querySelector('.home-promo-image img'));
    assert.equal(page.registry.size,3);assert.equal((await page.read()).inventory.length,3);
    for(const img of page.document.querySelectorAll('img'))assert.match(img.getAttribute('src'),/^data:image\/(webp|png|jpeg);base64,/);
    for(const view of ['profile','upgrades','games','referrals','crash','cases']){
      if(view==='crash'){await page.click('.bottom-nav [data-view="games"]');await page.click('.game-crash');}
      else await page.click(`.bottom-nav [data-view="${view}"]`);
      assert.equal(page.ctx.location.hash,'#'+view);assert.ok(page.document.querySelector('main').textContent.trim().length>20);
    }
    assert.equal(page.document.querySelectorAll('.case-card').length,19);
    assert.ok(page.document.querySelector('.cases-banner-photo img'));
    await page.click('[data-action="case-group"][data-group="free"]');
    assert.match(page.document.querySelector('.case-empty-free').textContent,/пока нет/);
    await page.click('[data-action="case-group"][data-group="paid"]');
    assert.equal(page.document.querySelectorAll('.case-card').length,19);
  }finally{page.close();}
});

test('new mini app starts at zero and shows GRAM in profile',async()=>{
  const page=await launch({seeded:false});try{
    const initial=await page.read();assert.equal(initial.balance.stars,0);assert.equal(initial.balance.grams,0);
    await page.click('.bottom-nav [data-view="profile"]');
    assert.match(page.document.querySelector('.profile-balances').textContent,/GRAM/);
    assert.match(page.document.querySelector('.profile-balances').textContent,/0/);
    await page.click('.bottom-nav [data-view="games"]');await page.click('.game-crash');
    assert.equal(page.document.querySelector('#crash-bet-button').dataset.stakeCurrency,'stars');
    await page.click('[data-action="crash-currency"][data-currency="grams"]');
    assert.equal(page.document.querySelector('#crash-bet-button').dataset.stakeCurrency,'grams');
  }finally{page.close();}
});

test('Crash updates the payout without replacing player rows or button artwork',async()=>{
  const page=await launch({portable:false});try{
    await page.click('.bottom-nav [data-view="games"]');await page.click('.game-crash');
    vm.runInContext(`const wager={id:'ui-wager',currency:'stars',stake:25,auto:0,status:'active',user:state.user,payout:50};
      const time=Date.now()/1000;state.crash={...state.crash,phase:'running',starts_at:time-1,server_time:time,multiplier:2,mine:wager,bets:[wager]};
      ClezzyCrash.accept(null,state.crash);ClezzyCrash.paint();`,page.ctx);
    const row=page.document.querySelector('.crash-player'),art=page.document.querySelector('#crash-bet-button .currency-icon');
    assert.ok(row);assert.ok(art);
    vm.runInContext(`const previous=state.crash;const nextWager={...previous.mine,payout:62.5};
      state={...state,crash:{...previous,server_time:previous.server_time+.5,multiplier:2.5,mine:nextWager,bets:[nextWager]}};
      ClezzyCrash.accept(previous,state.crash);ClezzyCrash.paint();`,page.ctx);
    await until(()=>row.querySelector('.current-factor').textContent==='2.50');
    assert.equal(page.document.querySelector('.crash-player'),row);
    assert.equal(page.document.querySelector('#crash-bet-button .currency-icon'),art);
    assert.match(row.querySelector('.current-return').textContent,/62,5/);
    for(const id of ['crash-countdown-value','crash-label','crash-multiplier','crash-time','crash-end-value'])assert.ok(page.document.getElementById(id).closest('.crash-orbit'));
    let ticks=0;page.ctx.ClezzyCrash.tick=()=>ticks++;
    await page.click('.bottom-nav [data-view="cases"]');const before=ticks;
    await new Promise(resolve=>setTimeout(resolve,120));assert.equal(ticks,before);
  }finally{page.close();}
});

test('large inventories keep a bounded animation pool and prioritize the open gift',async()=>{
  const page=await launch({motion:true});try{
    vm.runInContext(`const original=state.inventory[0];state.inventory=Array.from({length:30},(_,i)=>({...original,id:9000+i}));navigate('profile');`,page.ctx);
    await until(()=>page.animationCalls.length>=4);
    assert.ok(vm.runInContext('animations.size<=7',page.ctx));
    assert.equal(vm.runInContext('[...animationNodes.values()].filter(info=>info.playing).length',page.ctx),4);
    await page.click('[data-action="gift-detail"][data-id="9000"]');
    await until(()=>page.animationCalls.some(options=>page.document.querySelector('#modal-content').contains(options.container)));
    assert.ok(vm.runInContext('animations.size<=7',page.ctx));
    assert.equal(vm.runInContext('[...animationNodes.values()].filter(info=>info.playing).length',page.ctx),1);
    await page.click('[data-action="close-modal"]');
    await until(()=>vm.runInContext('[...animationNodes.values()].filter(info=>info.playing).length',page.ctx)===4);
  }finally{page.close();}
});

test('Crash NFT selector submits a collectible wager and shows the exact edition',async()=>{
  const page=await launch({motion:true});try{
    await page.click('.bottom-nav [data-view="profile"]');
    const source=(await page.read()).inventory.find(i=>i.gift_id==='scaredcat');
    await page.click(`[data-action="gift-detail"][data-id="${source.id}"]`);
    await page.click('[data-action="item-collectible"]');
    await until(async()=> (await page.read()).inventory.some(i=>i.gift_id==='scaredcat-nft'));
    const nft=(await page.read()).inventory.find(i=>i.gift_id==='scaredcat-nft');
    await page.click('.bottom-nav [data-view="games"]');await page.click('.game-crash');
    await page.click('[data-action="crash-currency"][data-currency="nft"]');
    assert.equal(page.document.querySelectorAll('.crash-nft-choice').length,3);
    await page.click(`[data-action="crash-nft-pick"][data-id="${nft.id}"]`);
    assert.match(page.document.querySelector('.crash-nft-choice.selected').textContent,new RegExp('#'+nft.number));
    await page.submit('#crash-form',{auto:''});
    await until(async()=> !(await page.read()).inventory.some(i=>i.id===nft.id));
    assert.match(page.document.querySelector('.crash-player').textContent,new RegExp('Scared Cat #'+nft.number));
    assert.equal(page.document.querySelector('#crash-bet-button').disabled,true);
  }finally{page.close();}
});

test('nested dist HTML loads classic scripts and uses its own directory',async()=>{
  const page=await launch({portable:false,url:'http://127.0.0.1:10643/projects/Clezzy_Gifts/public/index.html'});try{
    assert.ok(page.ctx.ClezzyReady);assert.equal(page.document.querySelectorAll('.game-poster').length,4);
    assert.match(page.document.querySelector('.home-promo-image img').getAttribute('src'),/home-gifts\.png$/);
    await page.click('.bottom-nav [data-view="cases"]');assert.equal(page.document.querySelectorAll('.case-card').length,19);
    assert.match(page.document.querySelector('.cases-banner-photo img').getAttribute('src'),/cases-home\.jpg$/);
    assert.deepEqual(page.requests,['http://127.0.0.1:10643/projects/Clezzy_Gifts/public/api/health']);
    for(const script of page.document.querySelectorAll('script[src]')){assert.equal(script.getAttribute('type'),null);assert.match(script.getAttribute('src'),/^\.\//);}
  }finally{page.close();}
});

test('offline buttons upgrade, sell, open cases and persist inventory',async()=>{
  const store=memory(),page=await launch({storage:store,motion:true});try{
    await page.click('.bottom-nav [data-view="profile"]');
    const cat=(await page.read()).inventory.find(i=>i.gift_id==='scaredcat');
    await page.click(`[data-action="gift-detail"][data-id="${cat.id}"]`);
    await page.click('[data-action="item-collectible"]');
    await until(async()=> (await page.read()).inventory.some(i=>i.gift_id==='scaredcat-nft'));
    assert.equal((await page.read()).balance.stars,1475);
    await until(()=>page.animationCalls.some(o=>o.animationData?.layers?.length));await until(()=>page.document.querySelector('.result-title')?.textContent.includes('НОВАЯ МОДЕЛЬ'));
    assert.ok(page.animationCalls.every(o=>o.animationData&&!o.path));
    await page.click('[data-action="item-sell"]');assert.equal((await page.read()).inventory.length,2);
    await page.click('.bottom-nav [data-view="cases"]');const before=(await page.read()).balance.stars;
    await page.click('[data-action="case-detail"][data-id="love"]');await page.click('[data-action="case-open"]');
    await until(()=>page.document.querySelector('[data-action="result-inventory"]'));
    const after=await page.read();assert.equal(after.balance.stars,before-lovePrice);assert.equal(after.inventory.length,3);
    const reopened=await launch({storage:store});try{assert.equal((await reopened.read()).balance.stars,after.balance.stars);assert.equal((await reopened.read()).inventory.length,3);}finally{reopened.close();}
  }finally{page.close();}
});

test('hashing and UUID fallback supports insecure previews and blocked storage',async()=>{
  const page=await launch({insecure:true,blockedStorage:true});try{
    assert.ok(page.ctx.ClezzyReady);const platform=page.ctx.ClezzyPlatform;
    for(const text of ['','abc','Подарок','a'.repeat(1000)])assert.equal(await platform.sha256(text),createHash('sha256').update(text).digest('hex'));
    for(const key of ['key','k'.repeat(100)])assert.equal(await platform.hmac(key,'gift'),createHmac('sha256',key).update('gift').digest('hex'));
    assert.match(platform.randomUUID(),/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    await assert.rejects(page.registry.get('open_gift_case').execute({case_id:'love'}),/Недостаточно/);
  }finally{page.close();}
});

test('promo, topup, admin, referrals and crash work through HTML forms',async()=>{
  const page=await launch();try{
    await page.click('[data-action="topup"]');await page.click('[data-action="topup-confirm"]');assert.equal((await page.read()).balance.stars,2000);
    await page.click('.wallet .add');await page.click('[data-action="topup-method"][data-currency="grams"]');
    await page.click('[data-action="topup-confirm"]');assert.equal((await page.read()).balance.grams,3.8);
    await page.click('.bottom-nav [data-view="profile"]');await page.click('[data-action="profile-tab"][data-tab="promo"]');
    await page.submit('#promo-form',{code:'CLEZZY50'});assert.equal((await page.read()).balance.stars,2050);
    await page.submit('#promo-form',{code:'/ClezzyKryt'});assert.match(page.document.querySelector('main').textContent,/Админ-панель/);
    await page.submit('#admin-grant-form',{user_id:'10001',kind:'stars',amount:'500',quantity:'1',reason:'Проверка'});assert.equal((await page.read()).balance.stars,2550);
    await page.click('.bottom-nav [data-view="referrals"]');await page.submit('#referral-form',{code:'MYGIFTS'});assert.equal(page.document.querySelector('#referral-form input').value,'MYGIFTS');
    await page.click('.bottom-nav [data-view="games"]');await page.click('.game-crash');await page.submit('#crash-form',{stake:'25',auto:'1.1'});
    assert.equal((await page.read()).balance.stars,2525);assert.ok(page.document.querySelector('#crash-multiplier'));assert.equal(page.document.querySelector('#crash-bet-button').disabled,true);assert.equal(page.document.querySelectorAll('.crash-player').length,1);
  }finally{page.close();}
});

test('cases rail shows only actual case openings with player avatar and prize',async()=>{
  const page=await launch({portable:false,url:'file:///Downloads/index.html'});
  try{
    await page.click('.bottom-nav [data-view="cases"]');
    assert.ok(page.document.querySelector('.case-live'));
    await until(()=>page.document.querySelector('.case-live-empty'));
    assert.equal(page.document.querySelectorAll('.case-live-card').length,0);
    await page.registry.get('open_gift_case').execute({case_id:'love',currency:'stars'});
    await until(()=>page.document.querySelectorAll('.case-live-card').length===1);
    const card=page.document.querySelector('.case-live-card');
    assert.match(card.textContent,/Демо-игрок/);
    assert.ok(card.querySelector('.avatar'));
    assert.ok(card.querySelector('.case-live-art img, .case-live-coin'));
  }finally{page.close();}
});

test('live GRAM amount opens exact invoice review and wallet picker above sheet',async()=>{
  const catalog=JSON.parse(fs.readFileSync(new URL('public/catalog.json',root),'utf8'));
  const backend=new Demo(catalog,memory());
  const state=await backend.state();state.demo=false;state.payments_enabled=true;
  const requests=[];
  const response=body=>({ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>body});
  const page=await launch({portable:false,url:'https://game.example/',fetcher:async(url,options)=>{
    const path=new URL(url).pathname;
    if(path==='/api/health')return response({ok:true,virtual_economy:true});
    if(path==='/catalog.json')return response(catalog);
    if(path==='/api/auth')return response({token:'live-session',state});
    if(path==='/api/payments/grams/invoice'){
      const body=JSON.parse(options.body);requests.push({path,body});
      return response({order_id:'gram-order',status:'pending',invoice_url:'https://t.me/$gram',xtr:2,credit:1.234567});
    }
    if(path==='/api/payments/stars/order/gram-order')return response({status:'paid'});
    if(path==='/api/me')return response({state:{...state,balance:{...state.balance,grams:1.234567}}});
    throw Error('Unexpected '+path);
  }});
  try{
    const dialog=page.document.querySelector('#modal');
    page.ctx.open=()=>({});
    await page.click('[data-action="topup"]');await page.click('[data-action="topup-method"][data-currency="grams"]');
    const sheet=page.document.querySelector('.topup-sheet');
    assert.match(sheet.textContent,/Количество игрового GRAM/);
    assert.doesNotMatch(sheet.querySelector('.topup-entry').textContent,/Stars/);
    const input=page.document.querySelector('#topup-value');input.value='1.234567';
    input.dispatchEvent(new page.Event('input',{bubbles:true}));
    await page.click('[data-action="topup-confirm"]');
    assert.match(page.document.querySelector('.topup-review-price').textContent,/2.*Stars/);
    await page.click('[data-action="topup-back"]');
    assert.equal(page.document.querySelector('#topup-value').value,'1.234567');
    let modalState;
    page.ctx.TON_CONNECT_UI={TonConnectUI:class{
      onStatusChange(){}onModalStateChange(cb){modalState=cb;}
      async openModal(){modalState({status:'opened'});}
    }};
    await page.click('[data-action="wallet-connect"]');
    assert.equal(dialog.dataset.mode,'nonmodal');assert.ok(dialog.classList.contains('wallet-dialog-bridge'));
    modalState({status:'closed'});
    assert.equal(dialog.dataset.mode,'modal');assert.ok(!dialog.classList.contains('wallet-dialog-bridge'));
    await page.click('[data-action="topup-confirm"]');
    await page.click('[data-action="topup-pay"]');
    await until(()=>requests.length===1);
    assert.deepEqual(requests,[{path:'/api/payments/grams/invoice',body:{amount_grams:1.234567}}]);
    await until(()=>!dialog.open);
    assert.equal((await page.read()).balance.grams,1.234567);
  }finally{page.close();}
});

test('a failing real server shows an error without silently entering the demo',async()=>{
  const page=await launch({portable:false,url:'https://game.example/index.html',fetcher:async()=>({ok:false,status:503,headers:{get:()=> 'application/json'}})});try{
    assert.ok(!page.ctx.ClezzyReady);assert.match(page.document.querySelector('#app').textContent,/Сервер временно недоступен/);assert.equal(page.storage.data.size,0);
  }finally{page.close();}
  const auth=await launch({portable:false,url:'https://game.example/index.html',fetcher:async path=>{
    if(path.endsWith('api/health'))return {ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>({ok:true,virtual_economy:true})};
    if(path.endsWith('catalog.json'))return {ok:true,json:async()=>JSON.parse(fs.readFileSync(new URL('public/catalog.json',root),'utf8'))};
    return {ok:false,status:401,json:async()=>({error:'Открой приложение в Telegram'})};
  }});try{assert.ok(!auth.ctx.ClezzyReady);assert.match(auth.document.querySelector('#app').textContent,/Открой приложение в Telegram/);assert.equal(auth.storage.data.size,0);}finally{auth.close();}
});


test('retry after two lost server responses reuses the pending operation key',async()=>{
  const catalog=JSON.parse(fs.readFileSync(new URL('public/catalog.json',root),'utf8'));
  const backend=new Demo(catalog,memory()),keys=[];backend.data.stars=150000;backend.data.grams=2500000;backend.save();
  const response=body=>({ok:true,status:200,headers:{get:()=> 'application/json'},json:async()=>body});
  const page=await launch({portable:false,url:'http://127.0.0.1:8000/',fetcher:async(url,options)=>{
    const path=new URL(url).pathname;
    if(path==='/api/health')return response({ok:true,virtual_economy:true});
    if(path==='/catalog.json')return response(catalog);
    if(path==='/api/auth')return response({token:'test-session',state:await backend.state()});
    if(path==='/api/cases/open'){
      const key=options.headers['Idempotency-Key'];keys.push(key);
      const result=await backend.request(path,JSON.parse(options.body),key);
      if(keys.length<3)throw Error('Simulated connection interruption');
      return response(result);
    }
    throw Error('Unexpected '+path);
  }});
  try{
    const open=page.registry.get('open_gift_case');
    await assert.rejects(open.execute({case_id:'love'}),/interruption/);
    await open.execute({case_id:'love'});
    assert.equal(keys.length,3);assert.equal(new Set(keys).size,1);
    assert.equal((await backend.state()).stats.cases,1);assert.equal((await page.read()).balance.stars,1500-lovePrice);
    assert.equal(page.storage.getItem('clezzy-pending-operation'),'null');
  }finally{page.close();}
});
