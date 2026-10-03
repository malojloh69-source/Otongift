#!/usr/bin/env python3
"""Build classic scripts and a portable offline HTML plus adjacent public/ media."""
from pathlib import Path
import base64,json,mimetypes,re,sys
ROOT=Path(__file__).resolve().parents[1];PUBLIC=ROOT/'public'
sys.path.insert(0,str(ROOT))
from asset_store import AssetStore
STORE=AssetStore(PUBLIC)
def script_json(value):
 return json.dumps(value,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
def script_source(value):return re.sub(r'</script',r'<\\/script',value,flags=re.I)
def data_url(path):return 'data:'+(mimetypes.guess_type(path)[0] or 'application/octet-stream')+';base64,'+base64.b64encode(STORE.read(path.relative_to(PUBLIC).as_posix())).decode()
def build():
 catalog=json.loads((PUBLIC/'catalog.json').read_text());embedded={'catalog':catalog,'animations':{},'assetData':{},'standalone':False,'assetBase':'./'}
 (PUBLIC/'catalog.js').write_text('globalThis.ClezzyEmbedded='+script_json(embedded)+';\n')
 demo=(PUBLIC/'demo.js').read_text().replace('export class Demo','class Demo')
 (PUBLIC/'demo.browser.js').write_text("(() => {\n'use strict';\n"+demo+'\nglobalThis.ClezzyDemo=Demo;\n})();\n')
 offline=json.loads(json.dumps(catalog));images={};packed={}
 def image(path):
  if path not in images:images[path]=data_url(PUBLIC/path.removeprefix('./'))
  return images[path]
 for item in offline['gifts']+offline['cases']:item['image']=image(item['image'])
 for name,path in list(offline['currency_icons'].items()):offline['currency_icons'][name]=image(path)
 for name in ('japan.png','cases.png','upgrades.png','crash.png','cases-banner.jpg','referrals-reference.png','cases-home.jpg','home-gifts.png','cases-tile.jpg'):
  image('./assets/promos/'+name)
 for a in offline.get('ui_animations',{}).values():
  if a.get('image'):a['image']=image(a['image'])
 # Masks must be embedded: file:// CSS masks are blocked by several browsers.
 for c in offline.get('collections',[]):
  for symbol in c['symbols']:image(symbol['image'])
 for g in catalog['gifts']+list(catalog.get('ui_animations',{}).values()):
  if g.get('animation'):
   src=STORE.text((Path(g['animation'].removeprefix('./')).with_suffix('.asset.js')).as_posix())
   value=json.loads(src[src.index(',')+1:src.rindex(')')]);packed[g['animation']]=value
 html=(PUBLIC/'index.html').read_text();css=(PUBLIC/'style.css').read_text();theme=(PUBLIC/'theme.css').read_text()
 css=css.replace('./assets/fonts/InterVariable.woff2',data_url(PUBLIC/'assets/fonts/InterVariable.woff2'))
 theme=theme.replace('./assets/ui/pepe-loading.png',data_url(PUBLIC/'assets/ui/pepe-loading.png'))
 html=html.replace('<link rel="stylesheet" href="./style.css">','<style>'+css+'</style>')
 html=html.replace('<link rel="stylesheet" href="./theme.css">','<style>'+theme+'</style>')
 payload={'catalog':offline,'animations':{},'assetData':packed,'imageData':images,'standalone':True,'assetBase':'./public/'}
 for name in ('compat.js','bootstrap.js','catalog.js','demo.browser.js','assets/pako_inflate.min.js','assets.js','assets/lottie.min.js','boot.js','crash.js','app.js'):
  source='globalThis.ClezzyEmbedded='+script_json(payload)+';' if name=='catalog.js' else (PUBLIC/name).read_text()
  html=html.replace(f'<script defer src="./{name}"></script>','')
  html=html.replace('</body>',f'<script data-component="{name}">'+script_source(source)+'</script>\n</body>')
 (ROOT/'index.html').write_text(html)
 print(f'Built portable index.html ({len(html.encode()):,} bytes); non-default model media loads from adjacent public/')
if __name__=='__main__':build()
