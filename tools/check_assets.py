#!/usr/bin/env python3
"""Verify catalogue references and original packed Lottie data with the standard library."""
from pathlib import Path
import base64,gzip,json,re
ROOT=Path(__file__).resolve().parents[1];PUBLIC=ROOT/'dist'
def check():
 c=json.loads((PUBLIC/'catalog.json').read_text());images=set(c['currency_icons'].values());animations=set()
 for x in c['gifts']+c['cases']+list(c.get('ui_animations',{}).values()):
  images.add(x['image'])
  if x.get('animation'):animations.add(x['animation'])
 for x in c['collections']:
  for m in x['models']:images.add(m['image']);animations.add(m['animation'])
  images.update(s['image'] for s in x['symbols'])
 for rel in images:
  data=(PUBLIC/rel.removeprefix('./')).read_bytes()
  assert data[:4]==b'RIFF' and data[8:12]==b'WEBP',f'Invalid image: {rel}'
 for rel in animations:
  script=(PUBLIC/rel.removeprefix('./')).with_suffix('.asset.js').read_text()
  parts=json.loads('['+script[script.index('(')+1:script.rindex(')')]+']')
  assert parts[0]==rel,f'Animation registration mismatch: {rel}'
  original=json.loads(gzip.decompress(base64.b64decode(parts[1])))
  assert original.get('layers') and original.get('fr',0)>0,f'Empty original animation: {rel}'
  assert all(not a.get('p') or a['p'].startswith('data:') for a in original.get('assets',[])),f'Non-local animation: {rel}'
 assert (PUBLIC/'assets/fonts/InterVariable.woff2').read_bytes()[:4]==b'wOF2'
 result={'images':len(images),'original_animations':len(animations),'font':'Inter WOFF2','errors':0}
 print(json.dumps(result));return result
if __name__=='__main__':check()
