#!/usr/bin/env python3
"""Apply verified ordinary gift bids, or transparently labelled game estimates.

The public payments.getStarGifts response contains mint prices and collectible
resale floors, but no ordinary gift buyback order book. Never call its stars
field a buyback quote. An operator can supply observed bids in the JSON file.
"""
from pathlib import Path
from datetime import datetime
import json, math

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'public/catalog.json'
QUOTES=ROOT/'tools/data/ordinary_buyback_quotes.json'

def update():
    cat=json.loads(CATALOG.read_text())
    quotes=json.loads(QUOTES.read_text()).get('quotes',[])
    by_id={}
    for q in quotes:
        gid=str(q['telegram_gift_id']);amount=q['bid_stars']
        if gid in by_id or type(amount) is not int or amount<=0 or not q['source'].startswith('https://'):
            raise ValueError('Invalid or duplicate ordinary gift bid: '+gid)
        datetime.fromisoformat(q['observed_at'].replace('Z','+00:00'))
        by_id[gid]=q
    floors={g['collection_id']:g for g in cat['gifts'] if g['collectible']}
    counts={'verified_bid':0,'collection_floor_estimate':0,'collection_game_estimate':0,'unconfirmed_estimate':0}
    for gift in cat['gifts']:
        if gift['collectible']:continue
        quote=by_id.get(str(gift.get('telegram_gift_id')))
        if quote:
            gift.update(price=quote['bid_stars'],price_kind='verified_ordinary_bid',price_source=quote['source'],price_observed_at=quote['observed_at'])
            counts['verified_bid']+=1
        else:
            nft=floors.get(gift.get('collection_id'))
            floor=nft.get('telegram_resell_min_stars') if nft else None
            if type(floor) is int and floor>0:
                # A regular gift plus its configured conversion fee should be
                # approximately equal to the matching collection's floor.
                # This is a virtual game valuation, never an ordinary bid.
                gift.update(price=max(1,floor-cat['upgrade_cost']),price_kind='game_estimate_from_collectible_floor',price_source=nft['price_source'],price_observed_at=nft['price_observed_at'])
                counts['collection_floor_estimate']+=1
            elif nft and type(nft.get('price')) is int and nft['price']>0:
                gift.update(price=max(1,nft['price']-cat['upgrade_cost']),price_kind='game_estimate_from_collectible_estimate')
                counts['collection_game_estimate']+=1
            else:
                gift.update(price=gift.get('telegram_stars',gift['price']),price_kind='game_estimate_without_bid')
                counts['unconfirmed_estimate']+=1
    known={str(g.get('telegram_gift_id')) for g in cat['gifts'] if not g['collectible']}
    if set(by_id)-known:raise ValueError('Unknown gift ID in bid file')
    gifts={g['id']:g for g in cat['gifts']}
    for case in cat['cases']:
        ordinary=[l for l in case['loot'] if l.get('type')!='currency']
        weight=sum(l['weight'] for l in ordinary)
        if weight!=9500:
            remaining=9500
            for i,loot in enumerate(ordinary):
                loot['weight']=max(1,round(loot['weight']*9500/weight)) if i<len(ordinary)-1 else remaining
                remaining-=loot['weight']
        value=sum(gifts[l['gift_id']]['price']*l['weight'] for l in ordinary)/10000
        maximum=max(gifts[l['gift_id']]['price'] for l in ordinary)
        price=25;bonus=1
        for _ in range(6):
            price=max(25,math.ceil(max((value+bonus*.05)/.90,maximum/8)/5)*5)
            bonus=max(1,round(price*.65))
        case['loot']=ordinary+[{'type':'currency','amount_stars':bonus,'weight':500}]
        case.update(price=price,rtp=round((value+bonus*.05)/price*100,2),max_prize=max(maximum,bonus),reward_kind='ordinary_or_balance')
        assert sum(l['weight'] for l in case['loot'])==10000
    cat.update(version=5,prices_are='Verified ordinary buyback bid where supplied, otherwise labelled game estimate near collectible value; virtual items',ordinary_price_report=counts)
    CATALOG.write_text(json.dumps(cat,ensure_ascii=False,separators=(',',':'))+'\n')
    path=ROOT/'CATALOG_REPORT.json';report=json.loads(path.read_text());report.update(prices=cat['prices_are'],ordinary_prices=counts,currency_case_rewards=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    sources=ROOT/'ASSET_SOURCES.json';d=json.loads(sources.read_text());d['ordinary_pricing']={'verified_bid_count':counts['verified_bid'],'fallback':'virtual ordinary value near collectible floor minus conversion fee; not an ordinary buyback bid','quotes_file':'tools/data/ordinary_buyback_quotes.json'}
    sources.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(counts))

if __name__=='__main__':update()
