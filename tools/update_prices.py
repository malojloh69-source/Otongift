#!/usr/bin/env python3
"""Apply Telegram's observed Stars fields; never convert a TON floor to Stars.

Use a verified payments.getStarGifts snapshot (or its public archive). Prices are
snapshots, not live offers. Preserve catalogue IDs and existing media/collections.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, math

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://github.com/ssamy2/TelegramGiftsAssests/blob/main/gifts_api_response.json'


def update(snapshot, observed_at):
    catalog_path = ROOT / 'public/catalog.json'
    catalog = json.loads(catalog_path.read_text())
    raw = snapshot.read_bytes()
    records = {str(r['id']): r for r in json.loads(raw)['star_gifts_full']['gifts']}
    # Correct labels using the original Telegram sticker's emoji, retaining IDs
    # used by saved inventories. A Birthday Cake used to be labelled Rocket.
    names = {'5170144170496491616': 'Birthday Cake', '5170564780938756245': 'Rocket',
             '5168043875654172773': 'Trophy', '5170521118301225164': 'Diamond',
             '6028601630662853006': 'Sparkling Wine'}
    by_id = {g['id']: g for g in catalog['gifts']}
    ordinary = {g.get('collection_id'): g for g in catalog['gifts'] if not g['collectible'] and g.get('collection_id')}
    missing = []
    for gift in catalog['gifts']:
        base = ordinary.get(gift.get('collection_id')) if gift['collectible'] else gift
        record = records.get((base or {}).get('telegram_gift_id'))
        if not record:
            gift['price_kind'] = 'virtual_estimate'
            missing.append(gift['id'])
            continue
        gift['price_source'] = SOURCE
        gift['price_observed_at'] = observed_at
        gift['telegram_sold_out'] = bool(record.get('sold_out'))
        gift['telegram_upgrade_stars'] = record.get('upgrade_stars')
        if gift['collectible']:
            floor = record.get('resell_min_stars')
            gift['telegram_resell_min_stars'] = floor
            gift['telegram_availability_resale'] = record.get('availability_resale')
            if type(floor) is int and floor > 0:
                gift.update(price=floor, price_kind='telegram_resale_floor')
            else:
                gift['price_kind'] = 'virtual_estimate'
                missing.append(gift['id'])
        else:
            price = record.get('stars')
            if type(price) is not int or price <= 0:
                raise ValueError('Unconfirmed ordinary gift price: ' + gift['id'])
            gift.update(price=price, telegram_stars=price, price_kind='telegram_original')
            if gift['telegram_gift_id'] in names:
                gift.update(name=names[gift['telegram_gift_id']], collection_name=names[gift['telegram_gift_id']])
    for case in catalog['cases']:
        loot = {}
        for entry in case['loot']:
            if entry.get('type')=='currency':continue
            gift = by_id[entry['gift_id']]
            gid = ordinary[gift['collection_id']]['id'] if gift['collectible'] else gift['id']
            # Keep the accessible 25-Star starter case; its former Cake prize
            # was mispriced at 100 instead of the confirmed 500 Stars.
            if case['id'] == 'love' and gid in ('homemadecake', 'giftbox'):
                gid = 'rocket'  # Retained ID of the verified ordinary Birthday Cake.
            loot[gid] = loot.get(gid, 0) + entry['weight']
        case['loot'] = [{'gift_id': gid, 'weight': weight} for gid, weight in loot.items()]
        expected = sum(by_id[e['gift_id']]['price'] * e['weight'] for e in case['loot']) / 10000
        maximum = max(by_id[e['gift_id']]['price'] for e in case['loot'])
        case['price'] = 25 if case['id'] == 'love' else max(25, math.ceil(max(expected / .9, maximum / 8) / 5) * 5)
        # A very rare expensive ordinary prize can make the 8x cap force a low
        # RTP. Adjust configured weights rather than misprice that gift.
        if expected / case['price'] < .75:
            low = min(case['loot'], key=lambda e: by_id[e['gift_id']]['price'])
            high = max(case['loot'], key=lambda e: by_id[e['gift_id']]['price'])
            delta = by_id[high['gift_id']]['price'] - by_id[low['gift_id']]['price']
            if delta:
                shift = min(low['weight'] - 1, math.floor((case['price'] * .9 - expected) * 10000 / delta))
                if shift > 0:
                    low['weight'] -= shift
                    high['weight'] += shift
                    expected = sum(by_id[e['gift_id']]['price'] * e['weight'] for e in case['loot']) / 10000
        case.update(rtp=round(expected / case['price'] * 100, 2), max_prize=maximum, reward_kind='ordinary')
        if case.get('tag') == 'NFT':
            case['tag'] = None
    catalog.update(version=3, prices_are='Telegram original sale price / observed collection resale floor; virtual items',
                   price_snapshot={'observed_at': observed_at, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                                   'source': SOURCE, 'sha256': hashlib.sha256(raw).hexdigest(),
                                   'method': 'payments.getStarGifts: stars / resell_min_stars', 'unconfirmed': missing})
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, separators=(',', ':')) + '\n')
    report_path = ROOT / 'CATALOG_REPORT.json'
    report = json.loads(report_path.read_text())
    report.update(prices=catalog['prices_are'], price_snapshot=catalog['price_snapshot'], collectible_case_rewards=0)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    sources_path = ROOT / 'ASSET_SOURCES.json'
    if sources_path.is_file():
        sources = json.loads(sources_path.read_text())
        sources['price_snapshot'] = catalog['price_snapshot']
        sources_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'ordinary': len(records), 'collectible_floors': sum(g['price_kind'] == 'telegram_resale_floor' for g in catalog['gifts']),
                      'unconfirmed_prices': missing, 'cases': [(c['id'], c['price'], c['rtp']) for c in catalog['cases']]}, ensure_ascii=False))
    from update_market_prices import update as apply_ordinary_bids
    apply_ordinary_bids()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--observed-at', required=True, help='Verified snapshot timestamp, ISO-8601')
    args = parser.parse_args()
    update(args.snapshot, args.observed_at)
