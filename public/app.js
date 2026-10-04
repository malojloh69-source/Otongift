const $ = (q, root=document) => root.querySelector(q);
const $$ = (q, root=document) => [...root.querySelectorAll(q)];
const esc = s => String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = (n,d=2) => Number(n||0).toLocaleString('ru-RU',{maximumFractionDigits:d});
const delay = ms => new Promise(r=>setTimeout(r,ms));
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
let tg = window.Telegram?.WebApp;
const standalone=!!window.ClezzyEmbedded?.standalone;
const baseURL=new URL(window.ClezzyEmbedded?.assetBase||'.',document.baseURI||location.href||location.origin+'/');
const resourceURL=path=>new URL(path.replace(/^\/+/,''),baseURL).href;
const copyText=text=>window.ClezzyPlatform?ClezzyPlatform.copyText(text):navigator.clipboard.writeText(text);
async function fetchTimed(path,options={}){const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),6000);try{return await fetch(resourceURL(path),{...options,signal:controller.signal});}finally{clearTimeout(timer);}}
async function loadTelegram(){
  if(standalone||tg||!/[?&#]tgWebApp(Data|Platform|Version)=/.test(location.search+location.hash))return;
  await new Promise(resolve=>{const script=document.createElement('script');let timer;const done=()=>{clearTimeout(timer);resolve();};script.src='https://telegram.org/js/telegram-web-app.js';script.async=true;script.onload=done;script.onerror=done;timer=setTimeout(done,4000);document.head.append(script);});
  tg=window.Telegram?.WebApp;
}
const paths={
  cases:'<rect x="3" y="7" width="18" height="14" rx="3"/><path d="M3 12h18M9 7V4h6v3M10 11v4h4v-4"/>',
  games:'<rect x="3" y="3" width="18" height="18" rx="5"/><path d="m12 6 1.5 4.5L18 12l-4.5 1.5L12 18l-1.5-4.5L6 12l4.5-1.5z"/>',
  upgrade:'<path d="m5 13 7-7 7 7M5 20l7-7 7 7"/>',
  referrals:'<circle cx="7" cy="7" r="3"/><circle cx="17" cy="17" r="3"/><path d="m5 19 14-14"/>',
  crash:'<path d="M12 3c5 3 6 9 6 14l-6 4-6-4c0-5 1-11 6-14Z"/><circle cx="12" cy="10" r="2"/><path d="m6 14-3 4v3l3-2m12-5 3 4v3l-3-2M10 21v2m4-2v2"/>',
  profile:'<circle cx="12" cy="7" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2Z"/>',
  gift:'<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M5 12v9h14v-9M12 8v13"/><path d="M12 8H8a3 3 0 1 1 3-3l1 3Zm0 0h4a3 3 0 1 0-3-3l-1 3Z"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
  close:'<path d="m6 6 12 12M18 6 6 18"/>',
  chevron:'<path d="m9 5 7 7-7 7"/>',
  copy:'<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 4V3H3v13h1"/>',
  shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  wallet:'<path d="M21 8V5H5a3 3 0 0 0 0 6h16v9H5a3 3 0 0 1-3-3V8"/><path d="M21 11h-5v5h5"/>',
  crown:'<path d="m3 7 5 5 4-8 4 8 5-5-2 13H5Z"/>',
  admin:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><circle cx="12" cy="10" r="2"/><path d="M8 16a4 4 0 0 1 8 0"/>',
  bolt:'<path d="m13 2-9 12h7l-1 8 10-13h-7Z"/>',
  stars:'<path d="m12 3 3 6 6 1-4.5 4.5L18 21l-6-3-6 3 1.5-6.5L3 10l6-1Z"/>',
};
const icon = (name,cls='') => `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]||paths.gift}</svg>`;
const star=coin('stars');
const gram=coin('grams');
const NAV=[['cases','cases','Кейсы'],['upgrades','upgrade','Апгрейд'],['games','games','Игры'],['referrals','referrals','Рефералы'],['profile','profile','Профиль']];
const titles={games:'Игры',cases:'Кейсы',upgrades:'Апгрейды',profile:'Мой профиль',crash:'Краш',referrals:'Рефералы',admin:'Админ-панель'};
let catalog, gifts, state, demo, isDeviceDemo=false, accessToken='', view='games', currency='stars', filter='all', search='', profileTab='inventory', upgradeTab='mine', selectedSource=null,selectedTarget=null, preset=2, lastProof=null,adminUnlocked=false,modalRun=0,toastTimer,crashTimer,animationCount=0;
let collections=new Map(),openingCase=false,openingCollectible=false,previousNavIndex=2,shopFilter='ordinary',shopSearch='',shopLimit=24,caseGroup='paid';
let caseFeedItems=[],caseFeedTimer=null,caseFeedBusy=false,caseFeedError=false;
const animations=new Map();
// Keep SVG animations bounded on mobile, including when scrolling large inventories.
const lightDevice=(navigator.hardwareConcurrency||8)<=4||(navigator.deviceMemory||8)<=2;
document.documentElement.classList.toggle('light-device',lightDevice);
const animationLimit=lightDevice?3:4,retainedAnimationLimit=lightDevice?5:7;
const animationNodes=new Map();
let animationObserver=null,animationScheduled=false,animationLoads=0;
let renderedView='',crashFrame=null,lastCrashFrame=0;
const reelGeometry=new WeakMap();
const app=$('#app'),modal=$('#modal'),modalContent=$('#modal-content');

function toast(message){const t=$('#toast');t.textContent=message;t.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),3600);}
function haptic(type='light'){try{tg?.HapticFeedback?.impactOccurred(type);}catch{}}
function avatar(user,large=false){const name=user.first_name||'Игрок';return `<span class="avatar ${large?'large':''}">${user.photo_url?`<img src="${esc(user.photo_url)}" alt="Фото профиля" referrerpolicy="no-referrer">`:esc(Array.from(name)[0].toUpperCase())}</span>`;}
function giftArt(g,item=null,animate=true){const a=giftMeta(g,item),id='gift-animation-'+(++animationCount),bg=g.collectible?a.backdrop?.colors:null;return `<div class="gift-art ${g.collectible?'collectible':''}" data-model-id="${esc(a.model?.id||'')}" style="${bg?`background:radial-gradient(ellipse at 50% 35%,${esc(bg.centerColor)},${esc(bg.edgeColor)})`:''}">${g.collectible&&a.symbol?`<span class="gift-pattern" style="background-color:${esc(bg?.patternColor||'#fff')};mask-image:url('${assetURL(a.symbol.image)}');-webkit-mask-image:url('${assetURL(a.symbol.image)}')"></span>`:''}<img src="${esc(assetURL(a.image))}" alt="${esc(g.name)}${a.model?' · '+esc(a.model.name):''}" loading="lazy">${animate&&a.animation?`<div id="${id}" class="animation" data-animation="${esc(a.animation)}" aria-hidden="true"></div>`:''}${g.collectible?'<span class="gift-kind">ВИРТУАЛЬНЫЙ</span>':''}</div>`;}
function priceCurrency(item){return item?.acquisition_currency==='grams'||!item&&currency==='grams'&&(view==='cases'||view==='profile'&&profileTab==='shop')?'grams':'stars';}
function priceAmount(g,item){const c=priceCurrency(item);return item?.value??(c==='grams'?Math.ceil(g.price*1e6/catalog.stars_per_gram)/1e6:g.price);}
function itemPrice(g,item){const c=priceCurrency(item);return `${num(priceAmount(g,item),c==='grams'?3:2)} ${c==='grams'?gram:star}`;}
function giftCard(g,item=null,action='gift-detail',extra=''){const a=giftMeta(g,item),price=itemPrice(g,item);return `<button class="gift-card ${item?.id===selectedSource||g.id===selectedTarget?'selected':''}" data-action="${action}" data-id="${item?.id??g.id}" aria-label="${esc(g.name)} · ${num(priceAmount(g,item))} ${priceCurrency(item)==='grams'?'GRAM':'Stars'}">${giftArt(g,item)}<div class="gift-caption"><strong>${esc(g.name)}</strong><div class="serial">${g.collectible?esc(a.model?.name||g.model)+(item?.number?' · #'+item.number:''):g.upgrade_to?'Можно улучшить':'Обычный подарок'}</div><div class="gift-value"><span>${price}</span>${g.animation?icon('bolt','muted'):''}</div>${extra}</div></button>`;}
function empty(text,action='cases',label='Открыть кейсы'){return `<div class="empty">${icon('gift')}<p>${text}</p><button class="secondary" data-action="navigate" data-view="${action}">${label}</button></div>`;}

function releaseAnimation(node){const a=animations.get(node);if(a){a.destroy();animations.delete(node);}node.parentElement?.classList.remove('playing');const info=animationNodes.get(node);if(info)info.playing=false;}
function cleanAnimations(){for(const [node] of animationNodes){if(!node.isConnected){releaseAnimation(node);animationObserver?.unobserve(node);animationNodes.delete(node);}}}
function scheduleAnimations(){if(animationScheduled||reduced)return;animationScheduled=true;setTimeout(syncAnimations,0);}
function syncAnimations(){
  animationScheduled=false;cleanAnimations();
  const candidates=[...animationNodes].filter(([node,info])=>info.visible&&!info.failed&&!document.hidden&&(!modal.open||modalContent.contains(node)));
  candidates.sort(([a],[b])=>Number(modalContent.contains(b))-Number(modalContent.contains(a)));
  const wanted=new Set(candidates.slice(0,animationLimit).map(([node])=>node));
  for(const [node,info] of animationNodes){info.wanted=wanted.has(node);const a=animations.get(node);if(a&&info.playing!==info.wanted){info.wanted?a.play():a.pause();info.playing=info.wanted;}}
  for(const node of wanted){const info=animationNodes.get(node);if(animations.has(node)||info.loading||animationLoads>=2||!window.lottie)continue;
    info.loading=true;animationLoads++;
    (async()=>{try{
      const data=await ClezzyAssets.animation(node.dataset.animation);
      if(!node.isConnected||!info.wanted||document.hidden)return;
      for(const [old,a] of animations){if(animations.size<retainedAnimationLimit)break;if(!animationNodes.get(old)?.wanted)releaseAnimation(old);}
      if(animations.size>=retainedAnimationLimit)return;
      const a=lottie.loadAnimation({container:node,renderer:'svg',loop:true,autoplay:false,animationData:ClezzyPlatform.clone(data),rendererSettings:{preserveAspectRatio:'xMidYMid meet'}});
      animations.set(node,a);a.setSubframe?.(false);
      a.addEventListener('DOMLoaded',()=>{if(animations.get(node)===a)node.parentElement?.classList.add('playing');});
      a.addEventListener('data_failed',()=>{info.failed=true;releaseAnimation(node);scheduleAnimations();});
      if(animations.get(node)===a&&info.wanted){a.play();info.playing=true;}
    }catch{info.failed=true;}finally{info.loading=false;animationLoads--;scheduleAnimations();}})();
  }
}
function mountAnimations(root=document){
  cleanAnimations();if(reduced)return;
  if(!animationObserver&&'IntersectionObserver'in window)animationObserver=new IntersectionObserver(entries=>{for(const entry of entries){const info=animationNodes.get(entry.target);if(info)info.visible=entry.isIntersecting;}scheduleAnimations();},{rootMargin:'12px',threshold:.05});
  for(const node of $$('[data-animation]',root)){if(animationNodes.has(node))continue;animationNodes.set(node,{visible:!animationObserver,loading:false,playing:false,wanted:false,failed:false});animationObserver?.observe(node);}
  scheduleAnimations();
}
// The Crash visual clock runs only while its stage is actually on screen.
function syncCrashFrames(){
  if(view!=='crash'||document.hidden||modal.open){if(crashFrame!==null){if(window.cancelAnimationFrame)window.cancelAnimationFrame(crashFrame);else clearTimeout(crashFrame);}crashFrame=null;return;}
  if(crashFrame!==null)return;
  const request=window.requestAnimationFrame?fn=>window.requestAnimationFrame(fn):fn=>setTimeout(()=>fn(Date.now()),66);
  const frame=now=>{crashFrame=null;if(view!=='crash'||document.hidden||modal.open)return;if(now-lastCrashFrame>=66){ClezzyCrash.tick();lastCrashFrame=now;}crashFrame=request(frame);};
  lastCrashFrame=0;crashFrame=request(frame);
}

async function api(path,payload=null,key=null){const storage=ClezzyPlatform.storage();let requestKey=null;if(payload){let pending;try{pending=JSON.parse(storage.getItem('clezzy-pending-operation'));}catch{}if(pending?.user_id===state?.user?.id){if(pending.path!==path||JSON.stringify(pending.payload)!==JSON.stringify(payload))throw Error('Есть незавершённая операция. Повтори её или обнови страницу для восстановления.');requestKey=pending.key;}requestKey=key||requestKey||ClezzyPlatform.randomUUID();try{storage.setItem('clezzy-pending-operation',JSON.stringify({path,payload,key:requestKey,user_id:state?.user?.id}));}catch{}}let result;if(isDeviceDemo){try{result=await demo.request(path,payload||{},requestKey);}catch(error){if(payload)storage.setItem('clezzy-pending-operation','null');throw error;}}else{const options={method:payload?'POST':'GET',headers:{Authorization:'Bearer '+accessToken}};if(payload){options.headers['Content-Type']='application/json';options.headers['Idempotency-Key']=requestKey;options.body=JSON.stringify(payload);}let response;try{response=await fetchTimed(path,options);}catch(error){if(payload)response=await fetchTimed(path,options);else throw error;}result=await response.json();if(!response.ok){if(payload&&response.status<500)storage.setItem('clezzy-pending-operation','null');throw Error(result.error||'Ошибка сервера');}}if(result.state&&(!state?.crash||!result.state.crash||result.state.crash.server_time>=state.crash.server_time)){ClezzyCrash.accept(state?.crash,result.state.crash);state=result.state;}if(payload)try{storage.setItem('clezzy-pending-operation','null');if((result.gift&&!result.transferred)||result.reward)storage.setItem('clezzy-last-result',JSON.stringify({gift:result.gift,reward:result.reward,proof:result.proof,user_id:state.user.id}));}catch{}return result;}

function header(){const back=view!=='games';return `<header class="topbar"><div class="topbar-main">${back?`<button class="topbar-back" data-action="navigate" data-view="games" aria-label="Назад к играм">${icon('chevron')} <span>Назад</span></button>`:'<span class="topbar-spacer"></span>'}<button class="header-brand" data-action="navigate" data-view="games" aria-label="OtonGifts · Игры"><img src="${esc(assetURL('./assets/cases/blue.webp'))}" alt=""><strong><span>Oton</span>Gifts</strong></button><span class="topbar-spacer"></span></div><div class="user-strip"><button class="user-identity" data-action="navigate" data-view="profile" aria-label="Мой профиль">${avatar(state.user)}<span class="identity-copy"><strong>${esc(state.user.first_name||'Игрок')}</strong><small>${state.user.username?'@'+esc(state.user.username):'Мой профиль'}</small></span>${icon('chevron')}</button><div class="wallet"><div class="balance"><span id="balance-grams">${num(state.balance.grams,3)}</span>${gram}</div><div class="balance"><span id="balance-stars">${num(state.balance.stars)}</span>${star}</div><button class="add" data-action="topup" aria-label="Пополнить баланс">${icon('plus')}</button></div><button class="user-status" data-action="navigate" data-view="referrals" aria-label="Рефералы">${icon('referrals')}<span>${num(state.referral.invited)}</span></button></div></header>`;}
// Anchor navigation to the visible viewport, outside animated page containers.
function syncNavigationViewport(){const viewport=window.visualViewport;const offset=viewport&&viewport.scale===1?Math.max(0,(window.innerHeight||0)-viewport.height-viewport.offsetTop):0;document.documentElement.style.setProperty('--nav-viewport-offset',Math.round(offset)+'px');}
window.addEventListener?.('resize',syncNavigationViewport,{passive:true});
window.visualViewport?.addEventListener('resize',syncNavigationViewport,{passive:true});
window.visualViewport?.addEventListener('scroll',syncNavigationViewport,{passive:true});
function render(){const entering=renderedView!==view;renderedView=view;cleanAnimations();const foundIndex=NAV.findIndex(([v])=>v===view),navIndex=foundIndex<0?previousNavIndex:foundIndex;app.innerHTML=`<div class="shell"><aside class="sidebar"><a class="brand" href="#games" aria-label="OtonGifts"><span class="mark"><img src="${esc(assetURL('./assets/cases/blue.webp'))}" alt=""></span><strong>Oton<span>Gifts</span></strong></a><div class="side-label">ИГРЫ И ПОДАРКИ</div><nav class="side-nav" aria-label="Главное меню">${NAV.map(([v,i,label])=>`<button class="${view===v?'active':''}" data-action="navigate" data-view="${v}">${icon(i)}${label}</button>`).join('')}<button class="${view==='crash'?'active':''}" data-action="navigate" data-view="crash">${icon('crash')}Краш</button>${state.admin&&adminUnlocked?`<button class="${view==='admin'?'active':''}" data-action="navigate" data-view="admin">${icon('admin')}Админ-панель</button>`:''}</nav><div class="side-foot"><span class="demo-tag">${state.demo?'ДЕМО-РЕЖИМ':'ИГРОВОЙ РЕЖИМ'}</span><div>${icon('shield')} Проверяемая случайность</div><div class="line"></div><span>Игровые Stars и GRAM<br>Виртуальные коллекционные подарки</span><span style="color:#62626c">© 2026 OtonGifts</span></div></aside><div class="workspace">${header()}<main class="content ${entering?'page-enter':''} ${view==='cases'?'content-cases':''}" data-page="${view}">${page()}<div class="mode-strip">${icon('shield')}${isDeviceDemo?'Демо · баланс и подарки сохраняются только на этом устройстве':'Игровые балансы · коллекционные копии, без вывода в Telegram'}</div></main></div><nav class="bottom-nav" aria-label="Главное меню" style="--nav-index:${navIndex};--old-index:${previousNavIndex}"><i class="nav-indicator"></i>${NAV.map(([v,i,label])=>`<button class="${view===v?'active':''}" data-action="navigate" data-view="${v}" aria-current="${view===v?'page':'false'}">${icon(i)}<span>${label}</span></button>`).join('')}</nav></div>`;const nav=app.querySelector('.bottom-nav');document.querySelector('body > .bottom-nav')?.remove();if(nav)document.body.appendChild(nav);syncNavigationViewport();previousNavIndex=navIndex;mountAnimations(app);if(view==='crash')paintCrash();syncCrashFrames();syncCaseFeed();}
function page(){switch(view){case'games':return gamesPage();case'cases':return casesPage();case'upgrades':return upgradesPage();case'profile':return profilePage();case'crash':return crashPage();case'referrals':return referralsPage();case'admin':return adminPage();default:return gamesPage();}}

function promoImage(name){return esc(assetURL('./assets/promos/'+name));}
function gamesPage(){return `<button class="home-promo-image" data-action="navigate" data-view="cases" aria-label="Открыть каталог кейсов"><img src="${promoImage('home-gifts.png')}" alt="Коллекция подарков — открывай кейсы и находи своё" fetchpriority="high"></button><div class="games-overlap"><div class="section-head games-heading"><h2>Игры</h2></div><div class="games-grid"><button class="game-poster game-cases" data-action="navigate" data-view="cases" aria-label="Перейти к кейсам"><img src="${promoImage('cases-tile.jpg')}" alt="Кейсы — подарки внутри" loading="lazy"></button><button class="game-poster game-crash" data-action="navigate" data-view="crash" aria-label="Перейти в Краш"><img src="${promoImage('crash.png')}" alt="Краш" loading="lazy"></button><button class="game-poster game-upgrade" data-action="navigate" data-view="upgrades" aria-label="Перейти к апгрейдам"><img src="${promoImage('upgrades.png')}" alt="Апгрейды" loading="lazy"></button><button class="game-poster game-ref" data-action="navigate" data-view="referrals" aria-label="Перейти к рефералам"><img src="${promoImage('referrals-reference.png')}" alt="Рефералы" loading="lazy"></button></div></div>`;}

function caseFeedMarkup(){
 if(!caseFeedItems.length)return `<p class="case-live-empty">${caseFeedError?'Лента временно недоступна':'Пока нет открытий кейсов'}</p>`;
 return caseFeedItems.map(item=>{const user=item.user||{},prize=item.prize||{},gift=gifts.get(prize.gift_id),reward=prize.type==='currency';if(!reward&&!gift)return '';
  const name=reward?`${num(prize.amount,prize.currency==='grams'?3:0)} ${prize.currency==='grams'?'GRAM':'Stars'}`:gift.name;
  const art=reward?`<div class="case-live-coin">${prize.currency==='grams'?gram:star}</div>`:`<img src="${esc(assetURL(gift.image))}" alt="${esc(gift.name)}" loading="lazy">`;
  return `<article class="case-live-card" role="listitem" aria-label="${esc(user.first_name||'Игрок')}: ${esc(name)} из кейса ${esc(item.case_name||'Кейс')}"><strong class="case-live-name">${esc(user.first_name||'Игрок')}</strong><div class="case-live-art">${art}</div><div class="case-live-bottom">${avatar(user)}<span><strong>${esc(name)}</strong><small>${esc(item.case_name||'Кейс')}</small></span></div></article>`;
 }).join('');
}
function caseLiveStrip(){return `<section class="case-live" aria-label="Последние выпадения из кейсов"><div class="case-live-heading"><span class="case-live-dot"></span><strong>${isDeviceDemo?'Твои выпадения':'LIVE · Выпадения'}</strong><span>Последние открытия</span></div><div class="case-live-track" id="case-live-track" role="list" aria-live="polite">${caseFeedMarkup()}</div></section>`;}
async function refreshCaseFeed(){if(view!=='cases'||caseFeedBusy)return;caseFeedBusy=true;try{const result=await api('/api/cases/live');if(!Array.isArray(result.items))throw Error('Некорректная лента');const next=result.items,changed=JSON.stringify(next)!==JSON.stringify(caseFeedItems)||caseFeedError;caseFeedItems=next;caseFeedError=false;if(changed&&view==='cases'){const track=$('#case-live-track');if(track)track.innerHTML=caseFeedMarkup();}}catch{caseFeedError=true;if(!caseFeedItems.length&&view==='cases'){const track=$('#case-live-track');if(track)track.innerHTML=caseFeedMarkup();}}finally{caseFeedBusy=false;}}
function syncCaseFeed(){if(view!=='cases'){if(caseFeedTimer!==null){clearInterval(caseFeedTimer);caseFeedTimer=null;}return;}if(caseFeedTimer===null){void refreshCaseFeed();caseFeedTimer=setInterval(()=>{if(!document.hidden)void refreshCaseFeed();},12000);}}

function casesPage(){const list=visibleCases();return `${caseLiveStrip()}<button class="cases-banner-photo" data-action="case-scroll" aria-label="Перейти к каталогу кейсов"><img src="${promoImage('cases-home.jpg')}" alt="Кейсы — открывай кейсы и выбивай редкие подарки" fetchpriority="high"></button><section class="case-catalog"><div class="case-group-tabs" aria-label="Тип кейсов"><button class="${caseGroup==='paid'?'active':''}" data-action="case-group" data-group="paid">Платные</button><button class="${caseGroup==='free'?'active':''}" data-action="case-group" data-group="free">Бесплатные</button></div>${caseGroup==='free'?`<div class="case-empty-free">${icon('gift')}<h2>Бесплатных кейсов пока нет</h2><p>Все доступные сейчас кейсы находятся во вкладке «Платные».</p></div>`:`<div class="case-catalog-tools"><div class="segmented" aria-label="Валюта"><button class="${currency==='stars'?'active':''}" data-action="currency" data-currency="stars">${star} Stars</button><button class="${currency==='grams'?'active':''}" data-action="currency" data-currency="grams">${gram} GRAM</button></div><label class="search">${icon('search')}<input id="case-search" placeholder="Найти кейс" aria-label="Поиск кейсов" value="${esc(search)}"></label></div><div class="chips case-category" aria-label="Категории кейсов">${[['all','Все'],['starter','Старт'],['farm','Фарм'],['premium','Премиум']].map(([id,label])=>`<button class="chip ${filter===id?'active':''}" data-action="filter" data-filter="${id}">${label}</button>`).join('')}</div><div class="case-grid" id="case-grid">${caseCards(list)}</div>`}</section>`;}
function visibleCases(){return catalog.cases.filter(c=>(filter==='all'||c.category===filter)&&c.name.toLowerCase().includes(search.toLowerCase()));}
function caseCards(list){return list.length?list.map(c=>`<button class="case-card" data-action="case-detail" data-id="${c.id}" aria-label="${esc(c.name)}, открыть за ${currency==='stars'?num(c.price):num(c.price/catalog.stars_per_gram,3)} ${currency==='stars'?'Stars':'GRAM'}"><div class="case-art"><img src="${esc(assetURL(c.image))}" alt="${esc(c.name)}" loading="lazy"></div><div class="case-info"><h3>${esc(c.name)}</h3><div class="case-card-bottom"><div class="case-price"><span>${currency==='stars'?num(c.price):num(c.price/catalog.stars_per_gram,2)}</span>${currency==='stars'?star:gram}<small>${currency==='stars'?num(c.price/catalog.stars_per_gram,2):num(c.price)} ${currency==='stars'?gram:star}</small></div></div></div></button>`).join(''):'<p class="muted">Таких кейсов нет. Попробуйте другой запрос.</p>';}

function inventoryPage(){return `<div class="inventory-tools"><div class="inventory-value">Мои подарки <b>${state.inventory.length}</b><span class="muted"> · </span><b>${num(state.stats.inventory_value)} Stars</b></div><button class="secondary" data-action="sell-all" ${state.inventory.length?'':'disabled'}>Продать всё</button></div>${state.inventory.length?`<div class="gift-grid">${state.inventory.map(item=>giftCard(gifts.get(item.gift_id),item)).join('')}</div>`:empty('Пока нет подарков. Открой свой первый кейс.')}`;}
function historyPage(list=state.history){return list.length?`<div class="history">${list.map(e=>`<div class="history-row"><span class="history-icon">${icon(['upgrade','collectible'].includes(e.kind)?'upgrade':['crash','crash_bet'].includes(e.kind)?'crash':e.kind==='case'?'cases':e.kind==='promo'?'gift':'wallet')}</span><div class="history-copy"><strong>${esc(e.title)}</strong><p>${new Date(e.created*1000).toLocaleString('ru-RU',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})}${e.details?.gift_id?' · '+esc(gifts.get(e.details.gift_id)?.name||''):''}</p></div><span class="history-amount ${e.amount>=0?'green':''}">${e.amount>0?'+':''}${num(e.amount)} ${e.currency==='grams'?'GRAM':e.currency==='nft'?'NFT':'Stars'}</span>${e.details?.proof?`<button class="text-button" data-action="history-proof" data-index="${state.history.indexOf(e)}" aria-label="Проверить случайность">${icon('shield')}</button>`:''}</div>`).join('')}</div>`:empty('История появится после первой игры.');}
function profilePage(){const best=[...state.inventory].sort((a,b)=>(b.value_stars??gifts.get(b.gift_id).price)-(a.value_stars??gifts.get(a.gift_id).price))[0];const bg=best?gifts.get(best.gift_id):null;return `<section class="profile-hero"><div class="profile-user">${avatar(state.user,true)}<div><strong>${esc(state.user.first_name)}</strong><p>${state.user.username?'@'+esc(state.user.username):isDeviceDemo?'Гость · демонстрация':'Telegram ID '+state.user.id}</p></div></div><p class="muted small">Ваш баланс</p><div class="profile-balances"><div class="profile-balance-stars">${star}<strong>${num(state.balance.stars)}</strong><small>Stars</small></div><div class="profile-balance-grams">${gram}<strong>${num(state.balance.grams,3)}</strong><small>GRAM</small></div></div><div class="row profile-actions" style="justify-content:center"><button class="primary" data-action="topup">${icon('plus')} Пополнить</button><button class="secondary" data-action="profile-tab" data-tab="history" aria-label="История баланса">${icon('clock')}</button>${state.user.username?`<a class="secondary" href="https://t.me/${esc(state.user.username)}" target="_blank" rel="noopener">Telegram</a>`:''}</div></section><div class="profile-stats"><div class="stat-card"><span class="stat-icon">${icon('cases')}</span><strong>${state.stats.cases}</strong><p>Открыто кейсов</p></div><div class="stat-card"><span class="stat-icon">${icon('upgrade')}</span><strong>${state.stats.upgrades}</strong><p>Апгрейдов</p></div><div class="stat-card"><span class="stat-icon">${icon('gift')}</span><strong>${state.inventory.length}</strong><p>Подарков в инвентаре</p></div></div><section class="panel best-gift"><div><div class="row">${icon('crown','yellow')}<h3>Лучший подарок</h3></div><p>${bg?esc(bg.name)+' · '+num(best?.value??bg.price,best?.acquisition_currency==='grams'?3:2)+' '+(best?.acquisition_currency==='grams'?'GRAM':'Stars'):'Появится после первого выигрыша.'}</p><p class="small">Telegram ID: ${state.user.id}</p></div>${bg?giftArt(bg,best):icon('gift','muted')}</section><div class="profile-tabs" aria-label="Раздел профиля">${[['inventory','Инвентарь'],['shop','Магазин'],['history','История'],['promo','Промокод']].map(([id,label])=>`<button class="${profileTab===id?'active':''}" data-action="profile-tab" data-tab="${id}">${label}</button>`).join('')}</div>${profileTab==='inventory'?inventoryPage():profileTab==='history'?historyPage():profileTab==='shop'?shopPage():`<section class="panel promo-panel"><h3>Есть промокод?</h3><p class="hint" style="margin-top:9px">Введи код и получи подарок на баланс.</p><form id="promo-form"><div class="form-row"><input name="code" placeholder="ПРОМОКОД" autocomplete="off" required aria-label="Промокод"><button class="primary" type="submit">Активировать</button></div></form></section>`}`;}

function upgradesPage(){const source=state.inventory.find(i=>i.id===selectedSource),sg=source?gifts.get(source.gift_id):null,tgft=selectedTarget?gifts.get(selectedTarget):null;const sourceValue=source?.value_stars??sg?.price;const chance=sg&&tgft&&tgft.price>sourceValue?Math.min(95,Math.floor(sourceValue*9000/tgft.price)/100):0;const list=upgradeTab==='mine'?state.inventory.map(i=>({gift:gifts.get(i.gift_id),item:i})):catalog.gifts.filter(g=>!g.collectible&&(!sg||g.price>sourceValue)).map(g=>({gift:g,item:null}));return `<div class="page-head"><div><div class="eyebrow">${icon('upgrade')} УЛУЧШЕНИЕ ПОДАРКОВ</div><h1>Апгрейды</h1></div><button class="secondary" data-action="upgrade-info" aria-label="Правила апгрейда">${icon('shield')}</button></div><div class="upgrade-layout"><section class="upgrade-stage"><div class="wheel" style="--chance:${chance}"><div class="wheel-inner"><strong>${num(chance)}%</strong><small>Шанс улучшения</small></div><div class="needle" id="upgrade-needle"></div></div><div class="upgrade-pair"><button class="upgrade-slot ${sg?'':'empty-slot'}" data-action="pick-source" aria-label="Выбрать исходный подарок">${sg?giftArt(sg,source):icon('gift')}${sg?`<span class="slot-title">${esc(sg.name)} · ${itemPrice(sg,source)}</span>`:'Выбери свой подарок'}</button><div class="pair-icon">${icon('upgrade')}</div><button class="upgrade-slot ${tgft?'':'empty-slot'}" data-action="pick-target" aria-label="Выбрать желаемый подарок">${tgft?giftArt(tgft):icon('gift')}${tgft?`<span class="slot-title">${esc(tgft.name)} · ${num(tgft.price)} Stars</span>`:'Желаемый подарок'}</button></div><div class="presets">${[2,3,8].map(x=>`<button class="${preset===x?'active':''}" data-action="preset" data-value="${x}">x${x}</button>`).join('')}${[35,55,75].map(x=>`<button data-action="chance-preset" data-value="${x}">${x}%</button>`).join('')}</div><button class="primary full" data-action="upgrade-play" data-currency="${source?.acquisition_currency||'stars'}" ${chance?'':'disabled'}>${icon('upgrade')} Улучшить подарок</button><p class="upgrade-note">При неудаче исходный подарок сгорает.<br>Шанс = стоимость подарка / стоимость цели × 90%.</p></section><aside class="upgrade-sidebar"><section class="panel"><h3>Как это работает</h3><div class="stack"><p class="hint">Выбери обычный или коллекционный подарок из инвентаря, затем более дорогой обычный подарок.</p><p class="hint">Проверка результата доступна после апгрейда.</p><div style="height:1px;background:var(--border)"></div><p class="hint"><span class="yellow">Коллекционный подарок за ${catalog.upgrade_cost} Stars</span><br>Случайные модель, фон, узор и игровой номер доступны в инвентаре для подходящих подарков.</p><button class="secondary full" data-action="navigate" data-view="profile">Мой инвентарь</button></div></section></aside></div><div class="profile-tabs catalog-tabs">${[['mine','Мой инвентарь'],['targets','Желаемые подарки']].map(([id,label])=>`<button class="${upgradeTab===id?'active':''}" data-action="upgrade-tab" data-tab="${id}">${label}</button>`).join('')}</div><p class="selected-source">${upgradeTab==='mine'?'Выбери подарок для использования':'Выбери подарок, который хочешь получить'}</p>${list.length?`<div class="gift-grid">${list.map(({gift,item})=>giftCard(gift,item,upgradeTab==='mine'?'source-select':'target-select')).join('')}</div>`:empty('Инвентарь пуст. Подарки можно получить из кейсов.')}`;}

function crashPage(){return ClezzyCrash.page();}
function paintCrash(){ClezzyCrash.paint();}
async function pollCrash(){await ClezzyCrash.poll();}

function referralsPage(){return `<section class="ref-hero"><img src="${promoImage('referrals-reference.png')}" alt="Рефералы — приглашай друзей и получай награды"></section><div class="ref-actions"><button class="primary" data-action="ref-share">Пригласить друзей</button><button class="secondary" data-action="ref-copy" aria-label="Копировать приглашение">${icon('copy')}</button></div><p class="ref-explainer">Получай 25% от расчётной маржи игр друзей. Друг активирует код и получает 5 игровых Stars.</p><div class="ref-stats"><div class="stat-card"><strong>${state.referral.invited}</strong><p>Приглашено</p></div><div class="stat-card"><strong>${num(state.referral.earned)} ${star}</strong><p>Заработано</p></div></div><section class="panel"><h3>Свой промокод</h3><form id="referral-form"><div class="form-row"><input name="code" placeholder="МОЙ КОД" value="${esc(state.referral.code||'')}" aria-label="Ваш реферальный код" ${state.referral.code?'readonly':''} required minlength="4" maxlength="20"><button type="${state.referral.code?'button':'submit'}" class="primary" ${state.referral.code?'data-action="ref-copy"':''}>${state.referral.code?'Копировать':'Создать'}</button></div></form><p class="hint">Начисление рассчитывается от маржи, а не от всей ставки.</p></section><div class="section-head"><h2>История начислений</h2></div>${isDeviceDemo?'<p class="hint" style="margin-bottom:16px">В демоверсии приглашения не связывают разных пользователей.</p>':''}${historyPage(state.history.filter(e=>e.kind==='referral'))}`;}

function adminPage(){if(!state.admin)return '<div class="error-block">Доступ только для администратора.</div>';return `<div class="page-head"><div><div class="eyebrow">${icon('admin')} УПРАВЛЕНИЕ</div><h1>Админ-панель</h1></div></div><p class="admin-note">${isDeviceDemo?'Демо-панель меняет только данные этого устройства. Доступен пользователь '+state.user.id+'.':'Доступ подтверждён. Начисления сохраняются в журнале.'} Все начисления в этом проекте игровые.</p><div class="admin-layout"><section class="panel"><h3>Начисление и подарки</h3><form id="admin-grant-form" class="admin-form" style="margin-top:22px"><div class="field"><label>Telegram ID пользователя</label><input name="user_id" type="number" value="${state.user.id}" required></div><div class="field"><label>Что начислить</label><select name="kind" id="grant-kind"><option value="stars">Stars</option><option value="grams">GRAM</option><option value="gift">Коллекционный подарок</option></select></div><div class="field" id="grant-amount"><label>Количество валюты</label><input name="amount" type="number" min="0.01" max="1000000" step="0.01" value="1000"></div><div id="grant-gift" class="stack" hidden><div class="field"><label>Подарок</label><select name="gift_id">${catalog.gifts.map(g=>`<option value="${g.id}">${esc(g.name)}${g.collectible?' · '+esc(g.model):' · обычный'} · ${num(g.price)} Stars</option>`).join('')}</select></div><div class="field"><label>Количество подарков</label><input name="quantity" type="number" min="1" max="20" value="1"></div></div><div class="field"><label>Причина начисления</label><input name="reason" placeholder="Например, тестирование кейса" minlength="3" maxlength="250" required></div><button type="submit" class="primary">Начислить</button></form></section><section class="panel"><h3>Создать промокод</h3><form id="admin-promo-form" class="admin-form" style="margin-top:22px"><div class="field"><label>Промокод</label><input name="code" placeholder="OTON100" pattern="[A-Za-z0-9_]{4,24}" required></div><div class="field"><label>Награда · Stars</label><input name="reward" type="number" min="1" max="100000" value="100" required></div><div class="field"><label>Лимит активаций</label><input name="max_uses" type="number" min="1" max="1000000" value="100" required></div><button type="submit" class="primary">Создать промокод</button></form><div class="section-head"><h3>Пользователи</h3><button class="text-button" data-action="admin-users">Обновить</button></div><div id="admin-users"><p class="hint">Нажми «Обновить», чтобы получить список.</p></div></section></div>`;}

function showModal(html){modalRun++;modal.classList.toggle('case-dialog',html.includes('class="case-view"'));modalContent.innerHTML=html;cleanAnimations();if(!modal.open)modal.showModal();mountAnimations(modalContent);syncCrashFrames();return modalRun;}
const modalHead=title=>`<div class="modal-head"><h2>${esc(title)}</h2><button class="close-button" data-action="close-modal" aria-label="Закрыть">${icon('close')}</button></div>`;
function closeModal(){modalRun++;try{ClezzyPlatform.storage().setItem('clezzy-last-result','null');}catch{}modal.close();modal.classList.remove('wallet-dialog-bridge');modalContent.innerHTML='';cleanAnimations();scheduleAnimations();syncCrashFrames();}
function casePrize(loot){const units=Math.ceil(loot.amount_stars*1e6/catalog.stars_per_gram);return {currency,amount:currency==='stars'?loot.amount_stars:units/1e6};}
function caseChoice(loot){return loot.type==='currency'?{reward:casePrize(loot)}:{g:gifts.get(loot.gift_id),item:null};}
function caseTile(choice){
  if(choice.reward){const c=choice.reward.currency,coinIcon=c==='stars'?star:gram;return `<div class="roulette-tile"><div class="currency-art">${coinIcon}</div><div class="reel-caption">${num(choice.reward.amount,c==='stars'?0:3)} ${coinIcon}</div><div class="reel-tag">На баланс</div></div>`;}
  const {g,item}=choice;return `<div class="roulette-tile">${giftArt(g,item,false)}<div class="reel-caption">${currency==='stars'?num(g.price):num(g.price/catalog.stars_per_gram,3)} ${currency==='stars'?star:gram}</div><div class="reel-tag">${esc(g.name)}</div></div>`;
}
function caseLootCard(loot){return loot.type==='currency'?`<div class="gift-card currency-loot"><div class="currency-art">${currency==='stars'?star:gram}</div><div class="gift-caption"><strong>${num(casePrize(loot).amount,currency==='stars'?0:3)} ${currency==='stars'?'Stars':'GRAM'}</strong><div class="serial">На баланс</div></div></div>`:giftCard(gifts.get(loot.gift_id),null,'catalog-detail',``);}
function caseDetail(id){const c=catalog.cases.find(c=>c.id===id);if(!c)return;const pool=c.loot.map(caseChoice);showModal(caseScreen(c,Array.from({length:9},(_,i)=>pool[i%pool.length])));positionReel(4);}
async function openCase(id){
  if(openingCase)return;const c=catalog.cases.find(c=>c.id===id);if(!c)return;openingCase=true;
  const button=$('[data-action="case-open"]',modalContent);if(button)button.disabled=true;
  try{
    const r=await api('/api/cases/open',{case_id:id,currency,client_seed:'clezzy'});lastProof=r.proof;render();void refreshCaseFeed();
    const pool=c.loot.map(caseChoice),target=r.reward?{reward:r.reward}:{g:gifts.get(r.gift.gift_id),item:r.gift};
    const choices=Array.from({length:43},(_,i)=>i===34?target:pool[Math.floor(Math.random()*pool.length)]);
    const run=showModal(caseScreen(c,choices,true));positionReel(3);await preloadArt(choices);if(run!==modalRun)return;
    const track=$('.roulette-track',modalContent),wrap=$('.roulette-wrap',modalContent),geometry=measureReel(track,wrap),tiles=geometry.tiles.map(tile=>tile.el),width=geometry.width;
    const initial=width/2-geometry.tiles[3].center,stop=width/2-geometry.tiles[34].center;
    const start=Date.now(),duration=reduced?0:4900;if(!reduced)track.classList.add('spinning');
    await new Promise(resolve=>{const tick=()=>{if(run!==modalRun){resolve();return;}const t=duration?Math.min(1,(Date.now()-start)/duration):1,split=.14,x=t<split?t/split:(t-split)/(1-split),ease=t<split?2*split*(x**3-.5*x**4):split+2*(1-split)*(x-x**3+.5*x**4);paintReel(initial+(stop-initial)*ease,track,wrap);if(!reduced)track.style.setProperty('--motion-blur',(1.15*Math.sin(Math.PI*t)).toFixed(2)+'px');if(t<1)(window.requestAnimationFrame||((fn)=>setTimeout(fn,16)))(tick);else resolve();};tick();});
    if(run!==modalRun){toast(r.reward?'Приз начислен на баланс':'Подарок сохранён в инвентаре');return;}
    track.classList.remove('spinning');track.style.removeProperty('--motion-blur');positionReel(34);tiles[34].classList.add('winner');if(r.gift)tiles[34].querySelector('.gift-art').outerHTML=giftArt(target.g,r.gift);
    $('#case-outcome').innerHTML=caseWin(r);const again=$('[data-action="case-open"]',modalContent);again.disabled=false;
    again.innerHTML='Открыть ещё · '+priceText(c.price)+' '+(currency==='stars'?star:gram);
    $('#case-live-status').textContent=r.reward?'Приз начислен на баланс':'Подарок добавлен в инвентарь';mountAnimations(modalContent);haptic('medium');
  }catch(error){toast(error.message);if(button?.isConnected)button.disabled=false;}finally{openingCase=false;}
}
function resultModal(item,proof,label='ПОДАРОК ПОЛУЧЕН'){const g=gifts.get(item.gift_id),a=giftMeta(g,item);lastProof=proof||lastProof;showModal(`${modalHead('Подарок твой!')}<p class="result-title">${label}</p><div class="result-gift">${giftArt(g,item)}</div><div class="result-name"><h2>${esc(g.name)}</h2><p>${g.collectible?esc(a.model.name)+' · #'+item.number:g.upgrade_to?'Можно улучшить за '+catalog.upgrade_cost+' Stars':'Обычный подарок'}</p><p style="margin-top:12px;color:var(--blue);font-size:18px;font-weight:650">${itemPrice(g,item)}</p></div>${priceNote(g)}<div class="result-actions"><button class="primary" data-action="result-inventory">В инвентарь</button><button class="secondary" data-action="item-sell" data-id="${item.id}">Продать</button></div>${proof?'<button class="text-button full" style="margin-top:16px" data-action="last-proof">Проверить выпадение</button>':''}`);}
function giftDetail(id,fromCatalog=false){const item=fromCatalog?null:state.inventory.find(i=>i.id===Number(id)),g=fromCatalog?gifts.get(id):item?gifts.get(item.gift_id):null;if(!g)return;const a=giftMeta(g,item),c=collections.get(g.collection_id);showModal(`${modalHead(g.name)}<div class="result-gift">${giftArt(g,item)}</div><div class="result-name"><h2>${itemPrice(g,item)}</h2><p>${g.collectible?(item?'Коллекционный подарок #'+item.number:'Пример модели коллекции'):g.upgrade_to?'Можно улучшить':'Обычный подарок'}</p></div>${g.collectible?`<div class="gift-details"><div><small>Модель</small><strong>${esc(a.model.name)}</strong></div><div><small>Фон</small><strong>${esc(a.backdrop.name)}</strong></div><div><small>Узор</small><strong>${esc(a.symbol.name)}</strong></div></div>`:''}${item?.value_stars>g.price?`<p class="price-origin">Фон ${esc(a.backdrop?.name||'')}: игровая оценка +${String(item.attributes?.backdrop)==='49'?25:15}%. Это не котировка Getgems.</p>`:''}${item?`<div class="stack">${g.upgrade_to?`<button class="primary full" data-action="item-collectible" data-id="${item.id}">${icon('upgrade')} Улучшить за ${catalog.upgrade_cost} ${star}</button><p class="hint" style="text-align:center">Случайная модель из ${c?.models.length||0} вариантов коллекции</p>`:''}${!isDeviceDemo?`<button class="secondary full" data-action="item-transfer" data-id="${item.id}">Передать игроку</button>`:''}<div class="result-actions"><button class="secondary" data-action="item-use" data-id="${item.id}">В апгрейд</button><button class="secondary" data-action="item-sell" data-id="${item.id}">Продать</button></div></div>`:`${g.collectible?'<p class="hint" style="text-align:center;margin-top:15px">Коллекционные модели доступны через улучшение подарков.</p>':`<button class="primary full" data-action="shop-buy" data-id="${g.id}" data-currency="${currency}">Купить за ${itemPrice(g,null)}</button>`}`}${priceNote(g)}<p class="modal-warning">Виртуальный подарок и игровые Stars. Вывода в Telegram нет.</p><a class="text-button full" style="display:block;text-align:center;margin-top:8px" href="${esc(item?.attributes?.source||g.source_page)}" target="_blank" rel="noopener">Источник оригинальных материалов</a>`);}
function proofModal(proof){if(!proof){toast('Сыграй раунд, чтобы проверить результат');return;}showModal(`${modalHead('Проверка случайности')}<p class="hint">Сравни SHA-256(server seed) с хешем, опубликованным до игры. Затем вычисли HMAC-SHA256(seed, message).</p><div class="proof"><strong>Commitment</strong><br>${esc(proof.commitment)}<br><br><strong>Server seed</strong><br>${esc(proof.server_seed||'Откроется после завершения раунда')}<br><br><strong>Message</strong><br>${esc(proof.message||'')}<br><br>${proof.digest?'<strong>Digest</strong><br>'+esc(proof.digest)+'<br><br>':''}${proof.roll!==undefined?'Roll: '+proof.roll+' / 10000':proof.crash?'Crash: '+proof.crash+'x':''}</div><button class="secondary full" data-action="copy-proof">Копировать данные</button><p class="modal-warning">Проверка показывает соответствие результата опубликованному seed. Она не является независимым аудитом оператора.</p>`);lastProof=proof;}
let topupCurrency='stars',pendingPayment=null;
const topupDraft={stars:'',grams:''};
function topup(){
 const test=state.demo,enabled=state.payments_enabled;
 const grams=topupCurrency==='grams';
 showModal(`${modalHead('Пополнение')}<div class="topup-sheet"><div class="topup-handle"></div><div class="topup-methods" aria-label="Валюта пополнения"><button data-action="topup-method" data-currency="grams" aria-pressed="${grams}" class="${grams?'active':''}"><span class="topup-method-icon">${gram}</span><span><strong>GRAM</strong><small>Игровой баланс</small></span></button><button data-action="topup-method" data-currency="stars" aria-pressed="${!grams}" class="${!grams?'active':''}"><span class="topup-method-icon">${star}</span><span><strong>Telegram Stars</strong><small>Игровой баланс</small></span></button></div><label class="topup-entry"><span>${grams?'Количество игрового GRAM':test?'Количество игровых Stars':'Сумма к оплате · Telegram Stars'}</span><input id="topup-value" type="number" inputmode="decimal" min="${grams?(test?'0.01':'0.8'):(test?'1':'1')}" max="${grams?'80':test?'10000':'100'}" step="${grams?'0.000001':'1'}" placeholder="Введите сумму" value="${esc(topupDraft[topupCurrency]||(test?(grams?'1.3':'500'):''))}"></label><p class="topup-preview" id="topup-preview"></p><button class="primary full topup-submit" id="topup-confirm" data-action="topup-confirm">Пополнить</button><p class="topup-disclosure">${test?'Демо: реальные деньги не списываются.':grams?'Игровой GRAM начисляется после подтверждения оплаты ботом.':'Оплата через счёт Telegram Stars. Начисление после подтверждения ботом.'}</p>${grams?`<div class="wallet-connect"><div><strong>Подключить TON кошелёк</strong><p class="hint" id="wallet-state">Подключение показывает адрес. Перевод из кошелька не пополняет игровой баланс.</p></div><button class="secondary" data-action="wallet-connect">Подключить</button></div>`:''}${!test&&!enabled?'<p class="hint">Приём платежей пока недоступен.</p>':''}</div>`);
 updateTopupForm();
 const wallet=tonUI?.wallet?.account?.address;
 if(wallet)$('#wallet-state',modalContent).textContent='Подключено: '+wallet.slice(0,8)+'…'+wallet.slice(-6);
}
function updateTopupForm(){
 const input=$('#topup-value',modalContent),button=$('#topup-confirm',modalContent),preview=$('#topup-preview',modalContent);
 if(!input||!button)return;
 const test=state.demo,grams=topupCurrency==='grams',amount=Number(input.value);
 const valid=input.value!==''&&Number.isFinite(amount)&&amount>0&&(grams?amount<=(test?80:80)&&Number.isInteger(amount*1000000)&&amount>=(test?0.01:0.8):Number.isInteger(amount)&&amount<=(test?10000:100)&&amount>=1);
 const credit=test||grams?amount:amount*100;
 preview.textContent=valid?(test||grams?'Будет начислено ':'За '+num(amount,0)+' Telegram Stars будет начислено ')+num(credit,grams?6:0)+' игровых '+(grams?'GRAM':'Stars'):grams?'От 0,8 до 80 GRAM':'Минимум 1 Telegram Star';
 button.disabled=!valid||(!test&&!state.payments_enabled);
 button.textContent=test?'Получить '+(valid?num(credit,grams?6:0):'')+' '+(grams?'GRAM':'Stars'):grams?'Продолжить с GRAM':'Пополнить Stars';
 button.dataset.amount=valid?String(amount):'';button.dataset.currency=topupCurrency;
}
function reviewGramPayment(amount){
 const units=Math.round(amount*1000000),xtr=Math.ceil(units*catalog.stars_per_gram/100000000);
 pendingPayment={amount:units/1000000,xtr};
 showModal(`${modalHead('Подтверждение')}<div class="topup-sheet topup-review"><div class="topup-handle"></div><p>На игровой баланс поступит</p><strong class="topup-review-amount">${num(pendingPayment.amount,6)} ${gram} GRAM</strong><div class="topup-review-price"><span>К оплате через Telegram</span><strong>${num(xtr,0)} ${star} Stars</strong></div><p class="hint">Это покупка виртуального игрового GRAM. Перевод через TON кошелёк здесь не принимается.</p><p class="topup-preview" id="topup-preview"></p><button class="primary full topup-submit" data-action="topup-pay">Оплатить ${num(xtr,0)} ${star}</button><button class="secondary full" data-action="topup-back">Назад</button></div>`);
}
async function completeTelegramPayment(amount,targetCurrency){
 if(!state.payments_enabled||state.demo)throw Error('Платежи не настроены');
 const grams=targetCurrency==='grams',expectedXtr=grams?Math.ceil(Math.round(amount*1000000)*catalog.stars_per_gram/100000000):amount;
 const invoice=grams?await api('/api/payments/grams/invoice',{amount_grams:amount}):await api('/api/payments/stars/invoice',{amount_xtr:Number(amount),target_currency:'stars'});
 if(invoice.xtr!==expectedXtr||grams&&Math.abs(invoice.credit-amount)>0.0000001)throw Error('Цена счёта изменилась. Открой пополнение заново.');
 if(invoice.status==='paid'){await api('/api/me');closeModal();render();toast('Баланс уже начислен');return;}
 if(!invoice.invoice_url)throw Error('Счёт Telegram недоступен');
 if(tg?.openInvoice)tg.openInvoice(invoice.invoice_url,()=>{});else window.open(invoice.invoice_url,'_blank','noopener,noreferrer');
 const status=$('#topup-preview',modalContent);if(status)status.textContent='Ожидаем подтверждения Telegram…';
 for(let i=0;i<45;i++){
  await delay(1000);const response=await fetchTimed('api/payments/stars/order/'+invoice.order_id,{headers:{Authorization:'Bearer '+accessToken}});
  if(!response.ok)continue;const order=await response.json();
  if(order.status==='paid'){await api('/api/me');closeModal();render();toast('Начислено '+num(invoice.credit,targetCurrency==='grams'?6:0)+' игровых '+(targetCurrency==='stars'?'Stars':'GRAM'));return;}
  if(order.status==='refunded')throw Error('Платёж возвращён');
 }
 const button=$('[data-action="topup-pay"]')||$('#topup-confirm');if(button)button.disabled=false;
 toast('Счёт ожидает оплаты. Баланс обновится после подтверждения.');
}

let tonUI=null;
function restoreWalletSheet(){if(!modal.classList.contains('wallet-dialog-bridge'))return;modal.close();modal.classList.remove('wallet-dialog-bridge');if(modalContent.querySelector('.topup-sheet'))modal.showModal();}
async function connectWallet(){
 if(isDeviceDemo||location.protocol!=='https:')throw Error('Подключение кошелька доступно на HTTPS Mini App');
 if(!tonUI){
  if(!window.TON_CONNECT_UI){await new Promise((resolve,reject)=>{const s=document.createElement('script');s.src='https://unpkg.com/@tonconnect/ui@3.0.2/dist/tonconnect-ui.min.js';s.onload=resolve;s.onerror=()=>reject(Error('Не удалось загрузить TON Connect'));document.head.append(s);});}
  tonUI=new window.TON_CONNECT_UI.TonConnectUI({manifestUrl:location.origin+'/tonconnect-manifest.json'});
  tonUI.onStatusChange(wallet=>{const el=$('#wallet-state');if(el)el.textContent=wallet?.account?.address?'Подключено: '+wallet.account.address.slice(0,8)+'…'+wallet.account.address.slice(-6):'Кошелёк не подключён';});
  tonUI.onModalStateChange(info=>{if(info.status==='closed')restoreWalletSheet();});
 }
 // A modal <dialog> occupies the browser top layer and hides the SDK portal.
 // Keep the sheet visible as a fixed non-modal dialog while the wallet picker is open.
 if(modal.open){modal.close();modal.classList.add('wallet-dialog-bridge');modal.show();}
 try{await tonUI.openModal();}catch(error){restoreWalletSheet();throw error;}
}
function navigate(v){if(!titles[v])return;if(v==='admin'&&!state.admin){toast('Доступ только для администратора');return;}view=v;if(v==='admin')adminUnlocked=true;try{history.replaceState(null,'','#'+v);}catch{}render();window.scrollTo({top:0,behavior:'auto'});}
function chooseTarget(multiplier){const source=state.inventory.find(i=>i.id===selectedSource);if(!source){toast('Сначала выбери свой подарок');return;}const price=source.value_stars??gifts.get(source.gift_id).price;const choices=catalog.gifts.filter(g=>!g.collectible&&g.price>price).sort((a,b)=>Math.abs(a.price-price*multiplier)-Math.abs(b.price-price*multiplier));selectedTarget=choices[0]?.id||null;render();}
async function playUpgrade(){const source=selectedSource,target=selectedTarget;const button=$('[data-action="upgrade-play"]');if(!source||!target)return;if(button)button.disabled=true;try{const r=await api('/api/upgrades/play',{item_id:source,target_id:target,client_seed:'clezzy'});lastProof=r.proof;const stage=$('.upgrade-stage');if(!reduced)stage?.classList.add('is-spinning');const needle=$('#upgrade-needle');if(needle)needle.style.transform=`rotate(${1440+r.proof.roll/10000*360}deg)`;haptic();await delay(reduced?120:3250);render();if(r.win)resultModal(r.gift,r.proof,'УСПЕШНЫЙ АПГРЕЙД');else showModal(`${modalHead('Не в этот раз')}<div class="empty" style="padding:30px 0">${icon('upgrade')}<h2>Подарок сгорел</h2><p class="hint">Шанс был ${num(r.chance)}%. Результат: ${num(r.proof.roll/100)}%.</p><button class="primary" data-action="close-modal">Попробовать ещё</button><button class="text-button" data-action="last-proof">Проверить результат</button></div>`);}catch(error){toast(error.message);if(button)button.disabled=false;}}
async function shareReferral(copyOnly=false){if(!state.referral.code){toast('Сначала создай свой промокод');$('#referral-form input')?.focus();return;}const text=`Мой код ${state.referral.code} в OtonGifts — 5 игровых Stars для первого подарка.`;const botUser=catalog.bot_username;const link=botUser?`https://t.me/${botUser}?startapp=${state.referral.code}`:location.origin+'/#profile';if(copyOnly){try{await copyText(botUser?link:text);toast('Приглашение скопировано');}catch{toast(text);}}else if(tg?.openTelegramLink)tg.openTelegramLink('https://t.me/share/url?url='+encodeURIComponent(link)+'&text='+encodeURIComponent(text));else if(navigator.share){try{await navigator.share({title:'OtonGifts',text,url:link});}catch{}}else{try{await copyText(text+' '+link);toast('Приглашение скопировано');}catch{toast(text);}}}

document.addEventListener('click',async event=>{
  const b=event.target.closest('[data-action]');if(!b||b.disabled)return;const a=b.dataset.action,id=b.dataset.id;
  try{
    switch(a){
      case'navigate':navigate(b.dataset.view);break;
      case'filter':filter=b.dataset.filter;render();break;
      case'currency':currency=b.dataset.currency;render();break;
      case'case-detail':caseDetail(id);break;
      case'case-scroll':if(caseGroup==='free'){caseGroup='paid';render();}$('#case-grid')?.scrollIntoView?.({behavior:reduced?'instant':'smooth',block:'start'});break;
      case'case-group':caseGroup=b.dataset.group;render();break;
      case'case-open':await openCase(id);break;
      case'close-modal':closeModal();break;
      case'gift-detail':giftDetail(id);break;
      case'collection-models':collectionModels(id,b.dataset.group||'models');break;
      case'item-transfer':transferModal(id);break;
      case'shop-filter':shopFilter=b.dataset.filter;shopLimit=24;render();break;
      case'shop-more':shopLimit+=24;render();break;
      case'catalog-detail':giftDetail(id,true);break;
      case'result-inventory':closeModal();profileTab='inventory';navigate('profile');break;
      case'profile-tab':profileTab=b.dataset.tab;render();break;
      case'item-sell':b.disabled=true;await api('/api/inventory/sell',{item_ids:[Number(id)],currency:state.inventory.find(i=>i.id===Number(id))?.acquisition_currency||'stars'});closeModal();render();toast('Подарок продан');break;
      case'item-collectible':await upgradeCollectible(id,b);break;
      case'item-use':selectedSource=Number(id);selectedTarget=null;closeModal();navigate('upgrades');break;
      case'shop-buy':b.disabled=true;{const r=await api('/api/shop/buy',{gift_id:id,currency});render();resultModal(r.gift,null);}break;
      case'sell-all':showModal(`${modalHead('Продать все подарки?')}<p class="hint">${state.inventory.length} подарка за ${num(state.stats.inventory_value)} игровых Stars. После продажи эти экземпляры уйдут из инвентаря.</p><div class="result-actions" style="margin-top:24px"><button class="secondary" data-action="close-modal">Отмена</button><button class="primary" data-action="sell-all-confirm">Продать всё</button></div>`);break;
      case'sell-all-confirm':b.disabled=true;await api('/api/inventory/sell',{item_ids:state.inventory.map(i=>i.id),currency:'stars'});closeModal();render();toast('Подарки проданы');break;
      case'topup':topup();break;
      case'topup-method':topupCurrency=b.dataset.currency;topup();break;
      case'topup-confirm':b.disabled=true;if(state.demo){await api('/api/demo/topup',{amount:Number(b.dataset.amount),currency:b.dataset.currency});closeModal();render();toast('Тестовый баланс пополнен');}else if(b.dataset.currency==='grams')reviewGramPayment(Number(b.dataset.amount));else await completeTelegramPayment(Number(b.dataset.amount),'stars');break;
      case'topup-pay':b.disabled=true;await completeTelegramPayment(pendingPayment.amount,'grams');break;
      case'topup-back':topup();break;
      case'wallet-connect':await connectWallet();break;
      case'upgrade-tab':upgradeTab=b.dataset.tab;render();break;
      case'pick-source':upgradeTab='mine';render();$('.catalog-tabs')?.scrollIntoView({behavior:'smooth',block:'center'});break;
      case'pick-target':upgradeTab='targets';render();$('.catalog-tabs')?.scrollIntoView({behavior:'smooth',block:'center'});break;
      case'source-select':selectedSource=Number(id);selectedTarget=null;upgradeTab='targets';chooseTarget(preset);break;
      case'target-select':if(gifts.get(id)?.collectible)throw Error('Целью может быть только обычный подарок');selectedTarget=id;render();window.scrollTo({top:0,behavior:'smooth'});break;
      case'preset':preset=Number(b.dataset.value);chooseTarget(preset);break;
      case'chance-preset':chooseTarget(90/Number(b.dataset.value));break;
      case'upgrade-play':await playUpgrade();break;
      case'upgrade-info':showModal(`${modalHead('Два способа улучшить')}<div class="stack"><p class="hint"><strong class="yellow">Коллекционный подарок за ${catalog.upgrade_cost} Stars</strong><br>В инвентаре обычный подарок из подходящей коллекции получает модель, фон, символ и игровой номер. Результат гарантирован.</p><p class="hint"><strong class="yellow">Апгрейд в дорогой обычный подарок</strong><br>Исходным может быть обычный или коллекционный подарок. При успехе получаешь выбранную цель, при неудаче — ничего. Шанс всегда виден до игры.</p><p class="modal-warning">В этой версии выдаются игровые копии. Настоящее улучшение в Telegram требует существующего подарка и подтверждённого доступа к нему.</p></div>`);break;
      case'crash-stake':$('#crash-stake').value=b.dataset.amount;ClezzyCrash.stakeChanged();break;
      case'crash-currency':ClezzyCrash.setCurrency(b.dataset.currency);break;
      case'crash-nft-pick':ClezzyCrash.pickNFT(Number(id));break;
      case'crash-plus':ClezzyCrash.stepStake(1);break;
      case'crash-minus':ClezzyCrash.stepStake(-1);break;
      case'crash-max':ClezzyCrash.stepStake('max');break;
      case'crash-cashout':await ClezzyCrash.collect();break;
      case'crash-proof':ClezzyCrash.proof();break;
      case'crash-history-proof':ClezzyCrash.proof(Number(b.dataset.index));break;
      case'crash-settings':ClezzyCrash.options();break;
      case'crash-list':ClezzyCrash.setTab(b.dataset.tab);break;
      case'last-proof':proofModal(lastProof);break;
      case'history-proof':proofModal(state.history[Number(b.dataset.index)]?.details?.proof);break;
      case'copy-proof':await copyText(JSON.stringify(lastProof,null,2));toast('Данные скопированы');break;
      case'ref-copy':await shareReferral(true);break;
      case'ref-share':await shareReferral(false);break;
      case'admin-users':{const r=await api('/api/admin/users');$('#admin-users').innerHTML=r.users.map(u=>`<button class="history-row full" data-action="admin-target" data-id="${u.id}"><div class="history-copy"><strong>${esc(u.first_name)}</strong><p>ID ${u.id}${u.username?' · @'+esc(u.username):''}</p></div><span class="small">${num(u.stars)} Stars</span></button>`).join('');}break;
      case'admin-target':$('#admin-grant-form [name="user_id"]').value=id;toast('Пользователь выбран');break;
    }
  }catch(error){toast(error.message||'Не удалось выполнить операцию');if(b.isConnected)b.disabled=false;}
});
document.addEventListener('input',event=>{if(event.target.id==='topup-value'){topupDraft[topupCurrency]=event.target.value;updateTopupForm();}if(event.target.id==='crash-stake')ClezzyCrash.stakeChanged();if(event.target.id==='crash-auto')ClezzyCrash.autoChanged();if(event.target.id==='shop-search'){shopSearch=event.target.value;shopLimit=24;$('#shop-grid').innerHTML=shopCards();mountAnimations($('#shop-grid'));}if(event.target.id==='case-search'){search=event.target.value;$('#case-grid').innerHTML=caseCards(visibleCases());}});
document.addEventListener('change',event=>{if(event.target.id==='crash-options-currency')ClezzyCrash.optionCurrency(event.target);if(event.target.id==='grant-kind'){const gift=event.target.value==='gift';$('#grant-gift').hidden=!gift;$('#grant-amount').hidden=gift;}});
document.addEventListener('submit',async event=>{event.preventDefault();const f=event.target,p=Object.fromEntries(new FormData(f)),button=$('[type="submit"]',f);if(button?.disabled)return;if(button)button.disabled=true;try{
  if(f.id==='promo-form'){const r=await api('/api/promo/redeem',p);if(r.open_admin){navigate('admin');toast(isDeviceDemo?'Открыта тестовая админ-панель':'Доступ администратора подтверждён');}else{render();toast('Получено '+num(r.reward)+' Stars');}}
  else if(f.id==='transfer-form'){await api('/api/inventory/transfer',{item_id:Number(p.item_id),recipient_id:Number(p.recipient_id)});closeModal();render();toast('Подарок передан');}
  else if(f.id==='referral-form'){await api('/api/referrals/create',p);render();toast('Промокод создан');}
  else if(f.id==='crash-form'){await ClezzyCrash.bet(p);}
  else if(f.id==='crash-options'){ClezzyCrash.saveOptions(p);}
  else if(f.id==='admin-grant-form'){await api('/api/admin/grant',{...p,user_id:Number(p.user_id),amount:Number(p.amount),quantity:Number(p.quantity)});render();toast('Начисление сохранено');}
  else if(f.id==='admin-promo-form'){await api('/api/admin/promo',{...p,reward:Number(p.reward),max_uses:Number(p.max_uses)});render();toast('Промокод создан');}
}catch(error){toast(error.message);}finally{if(button?.isConnected){if(f.id==='crash-form')ClezzyCrash.paint();else button.disabled=false;}}});
modal.addEventListener('click',e=>{if(e.target===modal){const r=modal.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeModal();}});
modal.addEventListener('cancel',e=>{e.preventDefault();closeModal();});
document.addEventListener('visibilitychange',()=>{syncAnimations();syncCrashFrames();if(!document.hidden)pollCrash();});

function webmcp(){const context=document.modelContext;if(!context?.registerTool)return;const lifecycle=new AbortController();const register=t=>{try{Promise.resolve(context.registerTool(t,{signal:lifecycle.signal})).catch(()=>{});}catch{}};register({name:'read_gift_inventory',description:'Read current game inventory and balances. Collectibles are virtual copies.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true},execute:async()=>({balance:state.balance,inventory:state.inventory.map(i=>({...i,name:gifts.get(i.gift_id).name}))})});register({name:'navigate_gift_game',description:'Open cases, upgrades, crash, referrals or profile without placing a bet.',inputSchema:{type:'object',properties:{view:{type:'string',enum:['cases','upgrades','crash','referrals','profile']}},required:['view'],additionalProperties:false},annotations:{readOnlyHint:false},execute:async p=>{if(!['cases','upgrades','crash','referrals','profile'].includes(p?.view))throw Error('Unknown view');navigate(p.view);return {view};}});register({name:'open_gift_case',description:'Spend game balance to open one case; show the outcome and add its virtual gift to inventory.',inputSchema:{type:'object',properties:{case_id:{type:'string'},currency:{type:'string',enum:['stars','grams']}},required:['case_id'],additionalProperties:false},annotations:{readOnlyHint:false},execute:async p=>{if(!catalog.cases.some(c=>c.id===p?.case_id)||p.currency&&!['stars','grams'].includes(p.currency))throw Error('Invalid case or currency');const r=await api('/api/cases/open',{case_id:p.case_id,currency:p.currency||'stars',client_seed:'clezzy'});render();void refreshCaseFeed();if(r.gift)resultModal(r.gift,r.proof);else recoveredCaseReward(r.reward,r.proof);return {gift:r.gift,reward:r.reward,balance:state.balance};}});window.addEventListener('pagehide',()=>lifecycle.abort(),{once:true});}

async function init(){try{
  await loadTelegram();
  try{accessToken=sessionStorage.getItem('clezzy-session')||'';}catch{}
  let health=null,healthInfo=null;
  if(!standalone&&!['file:','content:','data:'].includes(location.protocol)){
    try{health=await fetchTimed('api/health');}catch{if(tg?.initData)throw Error('Сервер недоступен. Попробуйте снова.');}
    if(health?.status>=500)throw Error('Сервер временно недоступен. Попробуйте снова.');
    if(health?.ok&&health.headers.get('content-type')?.includes('application/json')){try{healthInfo=await health.json();}catch{}}
  }
  const server=healthInfo?.ok===true&&healthInfo?.virtual_economy===true;
  if(!server&&tg?.initData&&!standalone)throw Error('API приложения недоступен. Запусти main.py и проверь адрес Mini App.');
  if(server||!window.ClezzyEmbedded?.catalog){
    const response=await fetchTimed('catalog.json');if(!response.ok)throw Error('Каталог подарков недоступен');catalog=await response.json();
  }else catalog=window.ClezzyPlatform.clone(window.ClezzyEmbedded.catalog);
  for(const gift of catalog.gifts)for(const key of ['image','animation'])if(gift[key]?.startsWith('/assets/'))gift[key]='.'+gift[key];
  for(const c of catalog.cases)if(c.image?.startsWith('/assets/'))c.image='.'+c.image;
  gifts=new Map(catalog.gifts.map(g=>[g.id,g]));collections=new Map((catalog.collections||[]).map(c=>[c.id,c]));
  if(!server){if(!window.ClezzyDemo)throw Error('Не загрузились файлы приложения. Открой index.html из корня архива.');demo=new window.ClezzyDemo(catalog);isDeviceDemo=true;state=await demo.state();}
  else{const res=await fetchTimed('api/auth',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+accessToken},body:JSON.stringify({init_data:tg?.initData||''})});const body=await res.json();if(!res.ok)throw Error(body.error||'Не удалось войти');accessToken=body.token;state=body.state;try{sessionStorage.setItem('clezzy-session',accessToken);}catch{}}
  if(tg){tg.ready?.();tg.expand?.();tg.setHeaderColor?.('#080b10');tg.setBackgroundColor?.('#080b10');document.documentElement.style.setProperty('--tg-viewport',tg.viewportStableHeight+'px');}
  const requested=new URLSearchParams(location.search).get('view')||location.hash.slice(1);if(titles[requested]&&(requested!=='admin'||state.admin)){view=requested;adminUnlocked=view==='admin';}
  await delay(Math.max(0,(reduced?300:2650)-(Date.now()-(window.OtonBootStarted||Date.now()))));
  render();window.ClezzyReady=true;recoverOperation();clearTimeout(window.ClezzyBootTimer);webmcp();crashTimer=setInterval(pollCrash,1000);
  const referral=tg?.initDataUnsafe?.start_param;if(referral&&/^[A-Z0-9_]{4,20}$/.test(referral)&&!isDeviceDemo){try{await api('/api/promo/redeem',{code:referral});render();toast('Реферальный бонус получен');}catch{}}
}catch(error){clearTimeout(window.ClezzyBootTimer);app.innerHTML=`<div class="boot"><span class="boot-star">✦</span><strong>OtonGifts</strong><p class="error-block">${esc(error.message)}</p><button class="primary" id="reload-app">Открыть заново</button></div>`;$('#reload-app').addEventListener('click',()=>location.reload());}}

init();

function coin(name){const path=ClezzyEmbedded?.catalog?.currency_icons?.[name]||'./assets/icons/'+name+'.webp';return `<span class="${name==='stars'?'star':'gram'}-symbol"><img class="currency-icon" src="${esc(ClezzyAssets.url(path))}" alt="${name==='stars'?'Stars':'GRAM'}"></span>`;}
function assetURL(path){return ClezzyAssets.url(path);}
function giftMeta(g,item=null){const c=collections.get(g.collection_id),a=item?.attributes||{},model=c?.models.find(x=>x.id===a.model)||c?.models[0],backdrop=c?.backdrops.find(x=>x.id===a.backdrop)||c?.backdrops[0],symbol=c?.symbols.find(x=>x.id===a.symbol)||c?.symbols[0];return{model,backdrop,symbol,image:g.collectible&&model?model.image:g.image,animation:g.collectible&&model?model.animation:g.animation};}
function priceText(price){return currency==='stars'?num(price):num(Math.ceil(price*1000000/catalog.stars_per_gram)/1000000,3);}
function caseScreen(c,choices,opening=false){const amount=currency==='stars'?c.price:Math.ceil(c.price*1000000/catalog.stars_per_gram)/1000000,insufficient=state.balance[currency]<amount;return `<div class="case-view" data-currency="${currency}"><div class="case-view-head"><button class="case-back" data-action="close-modal">${icon('chevron')} Назад</button><strong>Oton<span>Gifts</span></strong><span class="small">${num(state.balance[currency],3)} ${currency==='stars'?star:gram}</span></div><section class="case-stage"><div class="reel-pointer"></div><div class="reel-particles"></div><div class="roulette-wrap"><div class="roulette-track">${choices.map(caseTile).join('')}</div></div></section><section class="case-sheet"><div class="sheet-handle"></div><div class="case-summary"><div><h2>${esc(c.name)}</h2><div class="case-cost">${currency==='stars'?star:gram} ${priceText(c.price)}</div><div class="case-mini-line">${icon('gift')} ${c.loot.length} вариантов</div></div><img src="${esc(assetURL(c.image))}" alt="${esc(c.name)}"></div><div id="case-outcome"></div><div class="section-head"><h3>Содержимое кейса</h3></div><div class="loot-grid">${c.loot.map(caseLootCard).join('')}</div><div class="case-live-status" id="case-live-status">${opening?'Открываем кейс…':(isDeviceDemo?'Демо · виртуальные подарки':'Выбери кейс и нажми «Открыть»')}</div><div class="case-bottom-action">${insufficient&&!opening?`<div class="case-insufficient">Не хватает ${num(amount-state.balance[currency],3)} ${currency==='stars'?'Stars':'GRAM'}</div><button class="primary full" data-action="topup">Пополнить баланс</button>`:`<button class="primary full" data-action="case-open" data-id="${c.id}" ${opening?'disabled':''}>${opening?'<span class="spinner"></span> Открываем':'Открыть за '+priceText(c.price)+' '+(currency==='stars'?star:gram)}</button>`}</div></section></div>`;}
function caseWin(r){if(r.reward)return `<div class="case-win-info"><div class="eyebrow">ПРИЗ НА БАЛАНСЕ</div><h3>${num(r.reward.amount,r.reward.currency==='stars'?0:3)} ${r.reward.currency==='stars'?'Stars':'GRAM'}</h3><p>Начислено в валюте открытия кейса.</p><button class="primary" data-action="close-modal">Готово</button><button class="text-button" data-action="last-proof">Проверить выпадение</button></div>`;const item=r.gift,g=gifts.get(item.gift_id),a=giftMeta(g,item);return `<div class="case-win-info"><div class="eyebrow">ТВОЙ ПОДАРОК</div><h3>${esc(g.name)}</h3><p>${g.collectible?esc(a.model.name)+' · #'+item.number:'Добавлен в твою коллекцию'}</p><div class="result-actions"><button class="primary" data-action="result-inventory">В инвентарь</button><button class="secondary" data-action="item-sell" data-id="${item.id}">Продать за ${itemPrice(g,item)}</button></div><button class="text-button" data-action="last-proof">Проверить выпадение</button></div>`;}
function measureReel(track,wrap){
  let geometry=reelGeometry.get(track);if(geometry)return geometry;
  const width=wrap.clientWidth||360,tiles=$$('.roulette-tile',track).map((el,index)=>{const size=el.offsetWidth||153;return {el,center:(el.offsetLeft||index*(size+17))+size/2,tilt:null,scale:null};});
  geometry={width,tiles,position:null};reelGeometry.set(track,geometry);return geometry;
}
function paintReel(position,track=$('.roulette-track',modalContent),wrap=$('.roulette-wrap',modalContent)){
  if(!track||!wrap)return;const geometry=measureReel(track,wrap),center=geometry.width/2;
  geometry.position=position;track.style.transform=`translate3d(${position.toFixed(2)}px,0,0)`;
  for(const tile of geometry.tiles){const delta=position+tile.center-center;if(Math.abs(delta)>center+180)continue;
    const tilt=Math.max(-13,Math.min(13,delta/19)).toFixed(2)+'deg',scale=Math.max(.86,1-Math.abs(delta)/2400).toFixed(3);
    if(tile.tilt!==tilt){tile.el.style.setProperty('--tilt',tilt);tile.tilt=tilt;}
    if(tile.scale!==scale){tile.el.style.setProperty('--scale',scale);tile.scale=scale;}
  }
}
function positionReel(index){const track=$('.roulette-track',modalContent),wrap=$('.roulette-wrap',modalContent);if(!track||!wrap)return;const geometry=measureReel(track,wrap),tile=geometry.tiles[index];if(tile)paintReel(geometry.width/2-tile.center,track,wrap);}
window.addEventListener?.('resize',()=>{const track=$('.roulette-track',modalContent),wrap=$('.roulette-wrap',modalContent);if(!track||!wrap)return;const old=reelGeometry.get(track);reelGeometry.delete(track);if(old)paintReel(old.position+(measureReel(track,wrap).width-old.width)/2,track,wrap);},{passive:true});
async function preloadArt(choices){if(typeof Image==='undefined')return;const paths=[...new Set(choices.filter(x=>x.g).map(({g,item})=>assetURL(giftMeta(g,item).image)))];await Promise.race([Promise.all(paths.map(src=>new Promise(resolve=>{const im=new Image();im.onload=im.onerror=resolve;im.src=src;}))),delay(1800)]);}
async function upgradeCollectible(id,button){
  if(openingCollectible)return;openingCollectible=true;button.disabled=true;
  try{
    const old=state.inventory.find(i=>i.id===Number(id)),before=gifts.get(old.gift_id);
    const r=await api('/api/inventory/upgrade',{item_id:Number(id)}),after=gifts.get(r.gift.gift_id);
    await preloadArt([{g:before,item:old},{g:after,item:r.gift}]);render();
    const run=showModal(`${modalHead('Улучшение подарка')}<div class="collectible-reveal" id="collectible-reveal"><div class="reveal-orbit"></div><div class="reveal-gift reveal-before">${giftArt(before,old)}</div><div class="reveal-gift reveal-after">${giftArt(after,r.gift)}</div><div class="reveal-scan"></div></div><div class="reveal-progress"><span></span></div><div class="case-live-status" id="reveal-status" aria-live="polite">Раскрываем модель коллекции…</div>`);
    await delay(reduced?0:850);
    if(run!==modalRun){toast('Улучшенный подарок сохранён в инвентаре');return;}
    $('#collectible-reveal').classList.add('show-after');haptic('medium');
    const attrs=giftMeta(after,r.gift);$('#reveal-status').textContent=attrs.model.name+' · #'+r.gift.number;
    await delay(reduced?0:1800);
    if(run===modalRun)resultModal(r.gift,null,'НОВАЯ МОДЕЛЬ КОЛЛЕКЦИИ');else toast('Улучшенный подарок сохранён в инвентаре');
  }catch(error){toast(error.message);if(button.isConnected)button.disabled=false;}
  finally{openingCollectible=false;}
}
function recoveredCaseReward(reward,proof){lastProof=proof;showModal(`${modalHead('Приз получен')}<div class="case-win-info"><div class="eyebrow">НА БАЛАНСЕ</div><h3>${num(reward.amount,reward.currency==='stars'?0:3)} ${reward.currency==='stars'?'Stars':'GRAM'}</h3><p>Приз из кейса уже начислен.</p><button class="primary full" data-action="close-modal">Готово</button></div>`);}
async function recoverOperation(){const storage=ClezzyPlatform.storage();let pending,last;try{pending=JSON.parse(storage.getItem('clezzy-pending-operation'));last=JSON.parse(storage.getItem('clezzy-last-result'));}catch{}if(pending?.user_id===state.user.id){try{const r=await api(pending.path,pending.payload,pending.key);render();if(r.gift&&!r.transferred)resultModal(r.gift,r.proof,'ВОССТАНОВЛЕННЫЙ РЕЗУЛЬТАТ');else if(r.reward)recoveredCaseReward(r.reward,r.proof);}catch(error){toast(error.message);}return;}if(last?.user_id===state.user.id){if(last.reward)recoveredCaseReward(last.reward,last.proof);else if(last.gift){const item=state.inventory.find(i=>i.id===last.gift.id);if(item)resultModal(item,last.proof,'ПОДАРОК УЖЕ В ИНВЕНТАРЕ');}}}
function shopGifts(){return catalog.gifts.filter(g=>(shopFilter==='ordinary'?!g.collectible:g.collectible)&&g.name.toLowerCase().includes(shopSearch.toLowerCase()));}
function shopCards(){return shopGifts().slice(0,shopLimit).map(g=>giftCard(g,null,'catalog-detail')).join('')||'<p class="hint">Подарки не найдены</p>';}
function shopPage(){return `<div class="segmented shop-currency" aria-label="Валюта магазина"><button class="${currency==='stars'?'active':''}" data-action="currency" data-currency="stars">${star} Stars</button><button class="${currency==='grams'?'active':''}" data-action="currency" data-currency="grams">${gram} GRAM</button></div><div class="chips"><button class="chip ${shopFilter==='ordinary'?'active':''}" data-action="shop-filter" data-filter="ordinary">Обычные</button><button class="chip ${shopFilter==='collectible'?'active':''}" data-action="shop-filter" data-filter="collectible">Коллекционные</button></div><label class="search catalog-search">${icon('search')}<input id="shop-search" placeholder="Поиск подарка" value="${esc(shopSearch)}"></label><div class="gift-grid" id="shop-grid">${shopCards()}</div>${shopGifts().length>shopLimit?'<button class="secondary full" style="margin-top:18px" data-action="shop-more">Показать ещё</button>':''}`;}
function collectionModels(id,group='models'){const c=collections.get(id);if(!c||!['models','backdrops','symbols'].includes(group))return;const g=catalog.gifts.find(g=>g.collectible&&g.collection_id===id),values=c[group].filter(x=>x.weight>0&&!x.crafted),total=values.reduce((n,x)=>n+x.weight,0);showModal(`${modalHead(c.name)}<div class="profile-tabs">${[['models','Модели'],['backdrops','Фоны'],['symbols','Узоры']].map(([key,title])=>`<button class="${key===group?'active':''}" data-action="collection-models" data-id="${id}" data-group="${key}">${title}</button>`).join('')}</div><p class="hint" style="margin:16px 0">${values.length} вариантов. Доступные варианты коллекции.</p><div class="loot-grid">${values.map(x=>`<div class="gift-card">${giftArt(g,{attributes:{[group==='models'?'model':group==='backdrops'?'backdrop':'symbol']:x.id}},false)}<div class="gift-caption"><strong>${esc(x.name)}</strong></div></div>`).join('')}</div>`);}
function transferModal(id){const item=state.inventory.find(i=>i.id===Number(id));if(!item)return;showModal(`${modalHead('Передать подарок')}<p class="hint">${esc(gifts.get(item.gift_id).name)}${item.number?' · #'+item.number:''}. Получатель должен быть зарегистрирован в приложении.</p><form id="transfer-form" class="stack" style="margin-top:18px"><input type="hidden" name="item_id" value="${item.id}"><label class="field">Telegram ID получателя<input name="recipient_id" type="number" min="1" required></label><button type="submit" class="primary full">Передать подарок</button></form>`);}

function priceNote(g){const stamp=g.price_observed_at?new Date(g.price_observed_at).toLocaleDateString('ru-RU',{timeZone:'UTC'}):'';const text={verified_ordinary_bid:'Подтверждённая котировка скупки обычного подарка.',game_estimate_from_collectible_floor:'Игровая оценка: минимум коллекции минус стоимость улучшения. Это не заявка на скупку обычного подарка.',game_estimate_from_collectible_estimate:'Игровая оценка: ориентир коллекционного варианта минус стоимость улучшения. Котировки нет.',game_estimate_without_bid:'Игровая оценка: подтверждённой котировки скупки нет.',user_set_game_price:'Игровая цена задана владельцем проекта.',telegram_original:'Цена выпуска Telegram, не цена скупки.',telegram_resale_floor:'Минимум перепродажи коллекции, не цена экземпляра.'};const source=/^https:\/\//.test(g.price_source||'')?` <a href="${esc(g.price_source)}" target="_blank" rel="noopener">Источник</a>`:'';return `<p class="price-origin">${text[g.price_kind]||'Игровая оценка.'}${stamp?' · снимок '+stamp:''}${source}</p>`;}
