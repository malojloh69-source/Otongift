import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {webcrypto} from 'node:crypto';
import {Demo} from '../dist/demo.js';
globalThis.crypto ??= webcrypto;
const catalog=JSON.parse(fs.readFileSync(new URL('../dist/catalog.json',import.meta.url)));
const fund=d=>{d.data.stars=150000;d.data.grams=2500000;for(const id of ['rose','toybear','scaredcat'])d.addGift(id);d.save();return d;};
const create=()=>{let data=null;return fund(new Demo(catalog,{getItem:()=>data,setItem:(_k,v)=>data=v},()=>1800000000));};

test('a new device profile has zero balances and an empty inventory',async()=>{
 const d=new Demo(catalog,{getItem:()=>null,setItem(){}},()=>1800000000),s=await d.state();
 assert.deepEqual(s.balance,{stars:0,grams:0});assert.deepEqual(s.inventory,[]);
});

test('GRAM case rewards keep GRAM pricing and Onyx Black increases game value',async()=>{
 const c=structuredClone(catalog);c.cases[0].loot=[{gift_id:'heart',weight:10000}];
 const d=fund(new Demo(c,{getItem:()=>null,setItem(){}},()=>1800000000));
 const item=(await d.request('/api/cases/open',{case_id:c.cases[0].id,currency:'grams'})).gift;
 assert.equal(item.acquisition_currency,'grams');assert.equal(item.value,Math.ceil(c.gifts.find(g=>g.id==='heart').price*1e6/c.stars_per_gram)/1e6);
 const stored=d.item(item.id);stored.gift_id='scaredcat-nft';stored.attributes={backdrop:'49'};
 const premium=(await d.state()).inventory.find(i=>i.id===item.id);
 assert.equal(premium.value_stars,Math.ceil(c.gifts.find(g=>g.id==='scaredcat-nft').price*1.25));
 assert.equal(premium.acquisition_currency,'grams');
});

test('a direct GRAM purchase records its GRAM valuation',async()=>{
 const d=create(),before=(await d.state()).balance.grams;
 const bought=await d.request('/api/shop/buy',{gift_id:'heart',currency:'grams'});
 assert.equal(bought.gift.acquisition_currency,'grams');
 assert.equal(bought.state.balance.grams,before-bought.gift.value);
});

test('device demo persists inventory and balance and checks expensive-case funds',async()=>{
 const d=create();const s=await d.state();assert.equal(s.balance.stars,1500);assert.equal(s.inventory.length,3);
 await assert.rejects(d.request('/api/cases/open',{case_id:'pepe'}),/Недостаточно/);
 assert.equal((await d.state()).balance.stars,1500);
 const r=await d.request('/api/cases/open',{case_id:'love'});assert.equal(r.state.balance.stars,1500-catalog.cases.find(c=>c.id==='love').price);assert.equal(r.state.inventory.length,4);
});
test('25 Star collectible formatting does not grant a real NFT',async()=>{
 const d=create();const s=await d.state();const cat=s.inventory.find(i=>i.gift_id==='scaredcat');
 const r=await d.request('/api/inventory/upgrade',{item_id:cat.id});assert.equal(r.gift.gift_id,'scaredcat-nft');assert.equal(r.gift.virtual,true);assert.equal(r.state.balance.stars,1475);
 await assert.rejects(d.request('/api/inventory/upgrade',{item_id:cat.id}));
});
test('promo and local demo admin complete real preview actions',async()=>{
 const d=create();await d.request('/api/promo/redeem',{code:'CLEZZY50'});
 await assert.rejects(d.request('/api/promo/redeem',{code:'CLEZZY50'}),/уже/);
 const admin=await d.request('/api/promo/redeem',{code:'/ClezzyKryt'});assert.ok(admin.open_admin);
 const r=await d.request('/api/admin/grant',{user_id:10001,kind:'gift',gift_id:'plushpepe-nft',quantity:1,reason:'Testing'});assert.ok(r.state.inventory.some(i=>i.gift_id==='plushpepe-nft'));
 await assert.rejects(d.request('/api/admin/grant',{user_id:123,kind:'stars',amount:100,reason:'Testing'}),/локальной/);
});
test('inventory sell cannot double-credit across concurrent clicks',async()=>{
 const d=create();const id=(await d.state()).inventory.find(i=>i.gift_id==='rose').id;
 const results=await Promise.allSettled([d.request('/api/inventory/sell',{item_ids:[id]}),d.request('/api/inventory/sell',{item_ids:[id]})]);
 assert.equal(results.filter(r=>r.status==='fulfilled').length,1);assert.equal((await d.state()).balance.stars,1525);
});
test('crash start, cashout and saved history',async()=>{
 const d=create();const r=await d.request('/api/crash/start',{stake:25,auto:0,currency:'stars'});assert.ok(r.round.commitment);assert.ok(!r.round.proof);
 const c=await d.request('/api/crash/cashout',{round_id:r.round.id});assert.ok(['crashed','cashed_out'].includes(c.round.status));assert.ok(c.round.proof);
});

test('collectible replay restores exact attributes and number without a second debit',async()=>{
 const d=create(),s=await d.state(),cat=s.inventory.find(i=>i.gift_id==='scaredcat'),p={item_id:cat.id};
 const results=await Promise.all([d.request('/api/inventory/upgrade',p,'upgrade-key-123'),d.request('/api/inventory/upgrade',p,'upgrade-key-123')]);assert.deepEqual(results[0],results[1]);assert.equal((await d.state()).balance.stars,1475);assert.equal((await d.state()).stats.upgrades,1);
 const item=results[0].gift,c=catalog.collections.find(c=>c.id===item.collection_id);assert.ok(item.number>=1&&item.number<=c.number_max);assert.ok(c.models.some(m=>m.id===item.attributes.model));
 await assert.rejects(d.request('/api/cases/open',{case_id:'love'},'upgrade-key-123'),/Ключ/);
});
test('demo exhaustion rolls back reservation, source gift and cost',async()=>{
 const tiny=structuredClone(catalog);tiny.collections.find(c=>c.id==='scared_cat').number_max=1;
 const d=fund(new Demo(tiny,{getItem:()=>null,setItem(){}},()=>1800000000)),s=await d.state(),cat=s.inventory.find(i=>i.gift_id==='scaredcat');await d.request('/api/inventory/upgrade',{item_id:cat.id});
 const duplicate=d.addGift('scaredcat'),before=await d.state();await assert.rejects(d.request('/api/inventory/upgrade',{item_id:duplicate.id}),/закончились/);assert.deepEqual(await d.state(),before);
});
