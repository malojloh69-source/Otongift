import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {webcrypto} from 'node:crypto';
import {Demo} from '../public/demo.js';
globalThis.crypto??=webcrypto;
const catalog=JSON.parse(fs.readFileSync(new URL('../public/catalog.json',import.meta.url)));
function fund(d){d.data.stars=150000;d.data.grams=2500000;for(const id of ['rose','toybear','scaredcat'])d.addGift(id);d.save();return d;}
function setup(){let now=1800000000;const store=new Map(),storage={getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)};const d=fund(new Demo(catalog,storage,()=>now));return {d,storage,setTime:n=>now=n,now:()=>now};}

test('offline Crash has the same room contract and never fabricates other players',async()=>{
 const {d}=setup(),s=await d.state(),r=s.crash;assert.equal(r.phase,'waiting');assert.deepEqual(r.bets,[]);assert.equal(r.players_count,0);assert.ok(r.commitment);assert.ok(!r.proof);
 const reply=await d.request('/api/crash/bet',{round_id:r.id,stake:25,currency:'stars',auto:0},'shared-bet-123');assert.equal(reply.state.balance.stars,1475);assert.equal(reply.bet.status,'queued');assert.equal(reply.state.crash.bets.length,1);assert.equal(reply.state.crash.bets[0].user.id,10001);assert.ok(!reply.state.crash.proof);
 await assert.rejects(d.request('/api/crash/bet',{round_id:r.id,stake:25,currency:'stars',auto:0},'second-bet-123'),/уже принята/);
});
test('offline replay and parallel requests reserve one wager',async()=>{
 const {d}=setup(),r=(await d.state()).crash,p={round_id:r.id,stake:25,currency:'stars'};
 const replies=await Promise.all([d.request('/api/crash/bet',p,'parallel-bet'),d.request('/api/crash/bet',p,'parallel-bet')]);assert.deepEqual(replies[0],replies[1]);assert.equal((await d.state()).balance.stars,1475);
 await assert.rejects(d.request('/api/crash/bet',{...p,stake:50},'parallel-bet'),/Ключ/);
});
test('offline exact cashout hides the shared seed until the final crash',async()=>{
 const {d,setTime}=setup(),r=(await d.state()).crash,internal=d.data.crashRooms[0];internal.crash=300;
 const bet=(await d.request('/api/crash/bet',{round_id:r.id,stake:25})).bet;await assert.rejects(d.request('/api/crash/collect',{bet_id:bet.id}),/ещё не начался/);
 setTime(r.starts_at+8*Math.log(1.25));const cash=await d.request('/api/crash/collect',{bet_id:bet.id},'cashout-123');assert.equal(cash.bet.cashout,1.25);assert.equal(cash.bet.payout,31.25);assert.equal(cash.state.balance.stars,1506.25);assert.ok(!cash.state.crash.proof);assert.ok(!JSON.stringify(cash).includes(internal.proof.server_seed));
 await d.request('/api/crash/collect',{bet_id:bet.id},'cashout-another');assert.equal((await d.state()).balance.stars,1506.25);
 setTime(r.starts_at+8*Math.log(3));const end=await d.state();assert.equal(end.crash.phase,'crashed');assert.equal(end.crash.proof.server_seed,internal.proof.server_seed);
});
test('offline auto settlement, losses and historical wagers survive reopening',async()=>{
 const {d,storage,setTime,now}=setup(),r=(await d.state()).crash;d.data.crashRooms[0].crash=150;
 await d.request('/api/crash/bet',{round_id:r.id,stake:.2,currency:'grams',auto:1.25});setTime(r.starts_at+40);
 const restored=new Demo(catalog,storage,now),s=await restored.state();assert.equal(s.balance.grams,2.55);assert.notEqual(s.crash.id,r.id);assert.equal(s.crash.last_round.bets[0].payout,.25);assert.equal(s.crash.last_round.bets[0].cashout,1.25);assert.equal(s.crash.last_round.id,r.id);
 const next=s.crash;restored.data.crashRooms[0].crash=150;const b=(await restored.request('/api/crash/bet',{round_id:next.id,stake:25,auto:1.5})).bet;setTime(next.starts_at+8*Math.log(1.5));const loss=await restored.request('/api/crash/collect',{bet_id:b.id});assert.equal(loss.bet.status,'lost');assert.equal(loss.bet.payout,0);assert.equal(loss.state.balance.stars,1475);
});
test('offline virtual NFT wager keeps its edition and awards an ordinary gift once',async()=>{
 const {d,storage,setTime,now}=setup();
 const source=(await d.state()).inventory.find(i=>i.gift_id==='scaredcat');
 const item=(await d.request('/api/inventory/upgrade',{item_id:source.id})).gift;
 const r=(await d.state()).crash;d.data.crashRooms[0].crash=300;
 const body={round_id:r.id,currency:'nft',item_id:item.id,auto:0};
 const start=(await d.state()).balance.stars;
 const first=await d.request('/api/crash/bet',body,'nft-bet-123');
 assert.deepEqual(await d.request('/api/crash/bet',body,'nft-bet-123'),first);
 assert.equal(first.state.balance.stars,start);
 assert.equal(first.bet.stake_item.number,item.number);
 assert.equal(first.bet.stake,item.value_stars);
 assert.ok(!first.state.inventory.some(i=>i.id===item.id));
 await assert.rejects(d.request('/api/inventory/sell',{item_ids:[item.id]}),/отсутствует/);
 const restored=new Demo(catalog,storage,now);
 assert.equal((await restored.state()).crash.bets[0].stake_item.number,item.number);
 setTime(r.starts_at+8*Math.log(1.25));
 const cash=await restored.request('/api/crash/collect',{bet_id:first.bet.id});
 assert.ok(cash.bet.reward_item);assert.ok(!catalog.gifts.find(g=>g.id===cash.bet.reward_item.gift_id).collectible);
 assert.ok(cash.bet.payout<=first.bet.stake*1.25);
 assert.equal(cash.state.balance.stars,start);
 assert.equal((await restored.request('/api/crash/collect',{bet_id:first.bet.id})).bet.reward_item.id,cash.bet.reward_item.id);
});
test('offline gift wager accepts an ordinary gift and consumes it on loss',async()=>{
 const {d,setTime}=setup(),r=(await d.state()).crash;
 const ordinary=(await d.state()).inventory.find(i=>i.gift_id==='rose');
 const start=(await d.state()).balance.stars;
 d.data.crashRooms[0].crash=150;
 const bet=await d.request('/api/crash/bet',{round_id:r.id,currency:'nft',item_id:ordinary.id});
 assert.equal(bet.bet.stake_item.number,null);
 setTime(r.starts_at+8*Math.log(1.5));
 const state=await d.state();assert.equal(state.crash.mine.status,'lost');
 assert.equal(state.balance.stars,start);assert.ok(!state.inventory.some(i=>i.id===ordinary.id));
});
test('offline cases reject collectible rewards and shop cannot bypass an upgrade',async()=>{
 const {d}=setup(),s=await d.state();await assert.rejects(d.request('/api/shop/buy',{gift_id:'scaredcat-nft'}),/через улучшение/);assert.equal((await d.state()).balance.stars,s.balance.stars);
 const c=structuredClone(catalog);c.cases[0].loot=[{gift_id:'scaredcat-nft',weight:10000}];const altered=fund(new Demo(c,{getItem:()=>null,setItem(){}},()=>1800000000));await assert.rejects(altered.request('/api/cases/open',{case_id:c.cases[0].id}),/недопустимый/);assert.equal((await altered.state()).balance.stars,1500);
 assert.ok(catalog.cases.every(c=>c.loot.every(l=>l.type==='currency'||!catalog.gifts.find(g=>g.id===l.gift_id).collectible)));
});
test('currency prize pays the selected case currency and replay cannot pay twice',async()=>{
 const c=structuredClone(catalog);c.cases[0].loot=[{type:'currency',amount_stars:15,weight:10000}];
 const d=fund(new Demo(c,{getItem:()=>null,setItem(){}},()=>1800000000));
 const star=await d.request('/api/cases/open',{case_id:'love',currency:'stars'},'stars-prize-123');
 assert.equal(star.gift,null);assert.equal(star.reward.amount,15);
 assert.deepEqual(await d.request('/api/cases/open',{case_id:'love',currency:'stars'},'stars-prize-123'),star);
 const gram=await d.request('/api/cases/open',{case_id:'love',currency:'grams'},'grams-prize-123');
 assert.equal(gram.reward.currency,'grams');assert.equal(gram.reward.amount,Math.ceil(15*1e6/c.stars_per_gram)/1e6);
 const cat=(await d.state()).inventory.find(i=>i.gift_id==='scaredcat');await d.request('/api/inventory/upgrade',{item_id:cat.id});
 const upgrade=await d.request('/api/upgrades/play',{item_id:cat.id,target_id:'preciouspeach'});
 assert.ok(upgrade.chance>0);assert.ok(!(await d.state()).inventory.some(i=>i.id===cat.id));
});
