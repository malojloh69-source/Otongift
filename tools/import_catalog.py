#!/usr/bin/env python3
"""Import verified Telegram gift media; virtual edition ranges come from its gift snapshot."""
from pathlib import Path
import json,re,base64,gzip,shutil,hashlib,urllib.request
ROOT=Path(__file__).resolve().parents[1];PUBLIC=ROOT/'dist';SOURCE='https://github.com/ssamy2/TelegramGiftsAssests'
def slug(x):return re.sub('[^a-z0-9]','',x.lower())
def weight(x):return max(0,round(float(x or 0)*100))
def pack(source,rel):
 data=source.read_bytes();data=data if data[:2]==b'\x1f\x8b' else gzip.compress(data,mtime=0);dest=(PUBLIC/rel.removeprefix('./')).with_suffix('.asset.js');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text('globalThis.ClezzyAsset('+json.dumps(rel)+','+json.dumps(base64.b64encode(data).decode())+');\n')
def build(source):
 old=json.loads((PUBLIC/'catalog.json').read_text());legacy={g['id']:g for g in old['gifts']};raw=json.loads((source/'gifts_api_response.json').read_text())['star_gifts_full']['gifts'];summary=json.loads((source/'Gifts_Details.json').read_text());details={str(x['regular_id']):x for x in summary['upgraded']};regular={str(x['id']):x for x in json.loads((source/'ss.json').read_text())};palettes={x['name']:x for x in json.loads((ROOT/'tools/data/backdrops.json').read_text())};gifts=[];collections=[];missing=[]
 common={'5170145012310081615':('heart','Heart'),'5170233102089322756':('teddy','Teddy Bear'),'5170250947678437525':('giftbox','Gift Box'),'5168103777563050263':('rose','Rose'),'5170144170496491616':('rocket','Birthday Cake'),'5170314324215857265':('flowers','Flowers'),'5170564780938756245':('cake','Rocket'),'5168043875654172773':('diamond','Trophy'),'5170690322832818290':('ring','Ring'),'5170521118301225164':('trophy','Diamond'),'6028601630662853006':('rainbowbear','Sparkling Wine')};aliases={slug(g.get('collection_name') or g['name']):g['id'] for g in legacy.values() if not g.get('collectible')};aliases.update({slug(k):v for k,v in {'Toy Bear':'toybear','Scared Cat':'scaredcat','Loot Bag':'lootbag','Durovs Cap':'durovscap','Heart Locket':'heartlocket','Plush Pepe':'plushpepe','Desk Calendar':'deskcalendar','Candy Cane':'candycane','Homemade Cake':'homemadecake'}.items()})
 for record in raw:
  gid=str(record['id']);d=details.get(gid);name=record.get('title') or (d or regular.get(gid,{})).get('full_name') or common.get(gid,('',f'Gift {gid}'))[1];iid=common[gid][0] if gid in common else aliases.get(slug(name),slug(name));base=dict(legacy.get(iid,{}));rel=f'./assets/originals/{gid}';dest=PUBLIC/(rel+'.webp').removeprefix('./');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/f'webp/by_id/{gid}.webp',dest);pack(source/f'tgs/by_id/{gid}.tgs',rel+'.tgs');base.update(id=iid,name=base.get('name') or name,collection_name=name,telegram_gift_id=gid,price=base.get('price') or max(1,int(record.get('stars') or 100)),telegram_stars=record.get('stars'),rarity=base.get('rarity','common'),image=rel+'.webp',animation=rel+'.tgs',collectible=False,virtual=True,upgrade_to=None,can_upgrade=False,source_page=base.get('source_page') or SOURCE,source_media=SOURCE+'/blob/main/webp/by_id/'+gid+'.webp')
  if d:
   short=d['short_name'];paths={k:source/f'{folder}/{short}/config.json' for k,folder in [('models','models'),('backdrops','backdrops'),('symbols','patterns')]};maximum=record.get('availability_total') or regular.get(gid,{}).get('supply')
   if maximum and all(p.exists() for p in paths.values()):
    models=[]
    for m in json.loads(paths['models'].read_text()):
     rarity=m.get('rarity_permille',m.get('rarity_percent'))
     if m.get('crafted') or weight(rarity)<=0:continue
     t=m['tgs_path'].removeprefix('TG_Photos_repo/');i=m['webp_path'].removeprefix('TG_Photos_repo/')
     if not (source/t).exists() or not (source/i).exists():missing.append({'collection':name,'model':m['name'],'reason':'source media unavailable'});continue
     dest=PUBLIC/('assets/'+i);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/i,dest);pack(source/t,'./assets/'+t);models.append({'id':str(m.get('model_id') or m.get('custom_emoji_id') or m['name']),'name':m['name'].replace('_',' ').title(),'weight':weight(rarity),'source_rarity':rarity,'image':'./assets/'+i,'animation':'./assets/'+t})
    backgrounds=[]
    for b in json.loads(paths['backdrops'].read_text()):
     p=palettes.get(b['name'])
     if p and weight(b.get('rarity_percent'))>0:backgrounds.append({'id':str(p['backdropId']),'name':b['name'],'weight':weight(b['rarity_percent']),'colors':p['hex']})
    symbols=[]
    for sy in json.loads(paths['symbols'].read_text()):
     sid=hashlib.sha256(sy['name'].encode()).hexdigest()[:16];image=f'./assets/symbols/{sid}.webp'
     if (PUBLIC/image.removeprefix('./')).exists() and weight(sy.get('rarity_percent'))>0:symbols.append({'id':sid,'name':sy['name'],'weight':weight(sy['rarity_percent']),'image':image})
    if models and backgrounds and symbols:
     c={'id':short,'name':name,'telegram_gift_id':gid,'number_max':int(maximum),'number_range_basis':'original gift supply; virtual editions only','models':models,'backdrops':backgrounds,'symbols':symbols,'source':SOURCE+'/tree/main/models/'+short};collections.append(c);nftid=iid+'-nft';base.update(collection_id=short,upgrade_to=nftid,can_upgrade=True);nft=dict(legacy.get(nftid,{}));nft.update(id=nftid,name=nft.get('name') or name,collection_name=name,collection_id=short,price=nft.get('price') or max(base['price']+25,base['price']*3),rarity=nft.get('rarity','rare'),image=models[0]['image'],animation=models[0]['animation'],collectible=True,virtual=True,can_upgrade=False,upgrade_to=None,model=models[0]['name'],backdrop=backgrounds[0]['name'],symbol=symbols[0]['name'],source_page=c['source'],source_media=c['source']);gifts.append(nft)
  gifts.append(base)
 byid={g['id']:g for g in gifts};ordered=[byid.pop(i) for i in legacy if i in byid]+list(byid.values());assert not ({l['gift_id'] for c in old['cases'] for l in c['loot'] if l.get('type')!='currency'}-{g['id'] for g in ordered});old.update(version=2,gifts=ordered,collections=collections,currency_icons={'stars':'./assets/icons/stars.webp','grams':'./assets/icons/grams.webp'},catalog_updated_at=summary['last_updated'],asset_sources=[SOURCE,'https://getgems.io/','https://api.changes.tg/','https://core.telegram.org/api/gifts']);(PUBLIC/'catalog.json').write_text(json.dumps(old,ensure_ascii=False,separators=(',',':'))+'\n');report={'ordinary_gifts':sum(not g['collectible'] for g in ordered),'collections':len(collections),'models':sum(len(c['models']) for c in collections),'snapshot':summary['last_updated'],'unavailable':missing,'ownership':'virtual','prices':'configured game valuations'};(ROOT/'CATALOG_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False),flush=True)
 # Reapply verified prices and ordinary-only case contents after every import.
 from update_prices import update
 from datetime import datetime,timezone
 update(source/'gifts_api_response.json',datetime.fromtimestamp(summary['last_updated'],timezone.utc).isoformat())
if __name__=='__main__':
 import sys;build(Path(sys.argv[1]))
