#!/usr/bin/env python3
"""OtonGifts: Telegram Mini App + virtual gift economy, Python 3.11+.

All authoritative game logic is in this file. No third-party dependencies.
Run: python main.py. Financial balances and collectible copies are virtual.
Actual Telegram/TON gift ownership is never fabricated by this application.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import logging
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from asset_store import AssetStore

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
ASSETS = AssetStore(PUBLIC)
LOG = logging.getLogger("clezzy")
WELCOME_BANNER = PUBLIC / "assets/promos/oton-welcome.png"
WELCOME_CAPTION = (
    "<b>🎉 Добро пожаловать в Oton Gift!</b>\n\n"
    "🚀 Играй в Ракетку и выигрывай редкие подарки\n"
    "🎁 Открывай кейсы и собирай гифты\n"
    "⬆️ Используй апгрейды и контракты\n"
    "🏆 Поднимайся в рейтинге и выигрывай призы\n\n"
    "👉 Начни играть прямо сейчас!"
)


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", key.strip()):
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env(ROOT / ".env")


class GameError(Exception):
    def __init__(self, message: str, status: int = 400):
        self.message, self.status = message, status
        super().__init__(message)


def integer(value, low=0, high=1_000_000) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"-?\d+", str(value)):
        raise GameError("Ожидается целое число")
    result = int(value)
    if not low <= result <= high:
        raise GameError(f"Число должно быть от {low} до {high}")
    return result


def amount_units(value, scale: int, maximum: int) -> int:
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount <= 0 or amount > maximum:
            raise GameError("Недопустимая сумма")
        units = int((amount * scale).to_integral_value(rounding=ROUND_DOWN))
        if Decimal(units) != amount * scale or units < 1:
            raise GameError("Слишком много знаков после запятой")
        return units
    except (InvalidOperation, ValueError, TypeError):
        raise GameError("Недопустимая сумма") from None


def validate_init_data(raw: str, bot_token: str, max_age=3600, now=None) -> dict:
    """Telegram HMAC validation, including signed fields and timestamp freshness."""
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
        if len(pairs) != len(dict(pairs)):
            raise ValueError("duplicate field")
        data = dict(pairs)
        received = data.pop("hash")
        check = "\n".join(f"{key}={data[key]}" for key in sorted(data))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not bot_token or not hmac.compare_digest(expected, received):
            raise ValueError("hash")
        age = (time.time() if now is None else now) - int(data["auth_date"])
        if age < -30 or age > max_age:
            raise ValueError("stale data")
        user = json.loads(data["user"])
        if type(user.get("id")) is not int or not 0 < user["id"] < 2 ** 52:
            raise ValueError("user")
        return user
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise GameError("Авторизация Telegram недействительна. Откройте приложение заново.", 401) from None


def telegram_api(token: str, method: str, payload: dict, timeout=35):
    if not token:
        raise GameError("Токен бота не настроен", 503)
    req = Request(f"https://api.telegram.org/bot{token}/{method}",
                  data=json.dumps(payload).encode(),
                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as response:
            result = json.load(response)
        if not result.get("ok"):
            raise GameError("Telegram отклонил операцию", 502)
        return result["result"]
    except (HTTPError, URLError, TimeoutError):
        # Never log the request URL: it contains the bot token.
        raise GameError("Telegram временно недоступен", 502) from None


def telegram_photo(token: str, chat_id: int, photo_path: Path, caption: str, reply_markup: dict):
    """Upload the bundled banner, so /start does not depend on Telegram fetching a URL."""
    if not token:
        raise GameError("Токен бота не настроен", 503)
    try:
        photo = photo_path.read_bytes()
    except OSError:
        raise GameError("Баннер приветствия не найден", 503) from None
    boundary = "OtonGifts" + secrets.token_hex(16)
    fields = {
        "chat_id": str(chat_id),
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(reply_markup, ensure_ascii=False),
    }
    parts = []
    for name, value in fields.items():
        parts.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                      value.encode("utf-8"), b"\r\n"))
    parts.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; '
                  'filename="oton-welcome.png"\r\nContent-Type: image/png\r\n\r\n'.encode(),
                  photo, b"\r\n", f'--{boundary}--\r\n'.encode()))
    req = Request(f"https://api.telegram.org/bot{token}/sendPhoto",
                  data=b"".join(parts),
                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    try:
        with urlopen(req, timeout=35) as response:
            result = json.load(response)
        if not result.get("ok"):
            raise GameError("Telegram отклонил операцию", 502)
        return result["result"]
    except (HTTPError, URLError, TimeoutError):
        # Never log the request URL: it contains the bot token.
        raise GameError("Telegram временно недоступен", 502) from None


def send_welcome(token: str, chat_id: int, mini_url: str):
    button = {"text": "🚀Играть", "style": "primary", "web_app": {"url": mini_url.rstrip("/") + "/"}}
    return telegram_photo(token, chat_id, WELCOME_BANNER, WELCOME_CAPTION,
                          {"inline_keyboard": [[button]]})


class Game:
    def __init__(self, database=None, demo=None, admin_ids=None, clock=time.time):
        self.database = str(database or os.environ.get("DATABASE_PATH", ROOT / "data/game.sqlite3"))
        self.demo = os.environ.get("DEMO_MODE", "true").lower() == "true" if demo is None else demo
        self.bot_token = os.environ.get("BOT_TOKEN", "")
        self.payments_enabled = not self.demo and bool(self.bot_token) and os.environ.get('ENABLE_STAR_PAYMENTS','false').lower()=='true'
        self.admin_ids = set(admin_ids if admin_ids is not None else
                             [int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()])
        self.clock = clock
        self.catalog = json.loads((PUBLIC / "catalog.json").read_text(encoding="utf-8"))
        self.gifts = {g["id"]: g for g in self.catalog["gifts"]}
        self.cases = {c["id"]: c for c in self.catalog["cases"]}
        self.collections = {c["id"]:c for c in self.catalog.get("collections",[])}
        self.rate = self.catalog["stars_per_gram"]
        self.rate_lock = threading.Lock()
        self.limits = {}
        self.validate_catalog()
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def validate_catalog(self):
        for gift in self.gifts.values():
            assert type(gift["price"]) is int and gift["price"] > 0
            if gift.get("upgrade_to"):
                assert gift["upgrade_to"] in self.gifts
        for case in self.cases.values():
            assert sum(x["weight"] for x in case["loot"]) == 10000
            expected = 0
            for loot in case["loot"]:
                assert 0 < loot["weight"] <= 10000
                if loot.get('type')=='currency':
                    assert type(loot.get('amount_stars')) is int and 0<loot['amount_stars']<=case['price']*8
                    price=loot['amount_stars']
                else:
                    gift = self.gifts[loot["gift_id"]]
                    assert not gift.get("collectible"), "Collectibles can only be obtained through upgrades"
                    price=gift['price']
                    assert price<=case['price']*8, "Case prize cap violated"
                expected+=price*loot['weight']/10000
            assert expected <= case["price"], "Negative house margin"

        assert isinstance(self.catalog.get("upgrade_cost",25),int) and self.catalog.get("upgrade_cost",25)>0
        for collection in self.collections.values():
            assert type(collection["number_max"]) is int and collection["number_max"]>0
            for group in ("models","backdrops","symbols"):
                values=collection[group]
                assert values and len({x["id"] for x in values})==len(values)
                assert all(type(x["weight"]) is int and x["weight"]>0 and not x.get("crafted") for x in values)
        for gift in self.gifts.values():
            if gift.get("collectible") or gift.get("upgrade_to"):
                assert gift["collection_id"] in self.collections

    @contextlib.contextmanager
    def db(self, write=False):
        db = sqlite3.connect(self.database, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def init_db(self):
        with sqlite3.connect(self.database) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users(
                  id INTEGER PRIMARY KEY, first_name TEXT NOT NULL, username TEXT,
                  photo_url TEXT, stars INTEGER NOT NULL DEFAULT 0 CHECK(stars>=0),
                  grams INTEGER NOT NULL DEFAULT 0 CHECK(grams>=0),
                  upgrades INTEGER NOT NULL DEFAULT 0, cases_opened INTEGER NOT NULL DEFAULT 0,
                  referrer INTEGER REFERENCES users(id), referral_code TEXT UNIQUE,
                  referral_earned INTEGER NOT NULL DEFAULT 0, server_seed TEXT NOT NULL,
                  nonce INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(
                  token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                  expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS inventory(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
                  gift_id TEXT NOT NULL, number INTEGER, status TEXT NOT NULL DEFAULT 'owned',
                  acquired REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_inventory_user_status ON inventory(user_id,status);
                CREATE TABLE IF NOT EXISTS events(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
                  kind TEXT NOT NULL, title TEXT NOT NULL, amount REAL NOT NULL,
                  currency TEXT NOT NULL DEFAULT 'stars', details TEXT NOT NULL DEFAULT '{}',
                  created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_events_user_created ON events(user_id,id DESC);
                CREATE TABLE IF NOT EXISTS requests(
                  user_id INTEGER NOT NULL REFERENCES users(id), key TEXT NOT NULL,
                  fingerprint TEXT NOT NULL, response TEXT NOT NULL, created REAL NOT NULL,
                  PRIMARY KEY(user_id,key));
                CREATE TABLE IF NOT EXISTS promos(
                  code TEXT PRIMARY KEY, reward INTEGER NOT NULL CHECK(reward>0),
                  max_uses INTEGER NOT NULL, uses INTEGER NOT NULL DEFAULT 0,
                  expires REAL, owner INTEGER REFERENCES users(id));
                CREATE TABLE IF NOT EXISTS redemptions(
                  code TEXT NOT NULL REFERENCES promos(code), user_id INTEGER NOT NULL REFERENCES users(id),
                  created REAL NOT NULL, PRIMARY KEY(code,user_id));
                CREATE TABLE IF NOT EXISTS rounds(
                  id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                  stake INTEGER NOT NULL CHECK(stake>0), currency TEXT NOT NULL,
                  seed TEXT NOT NULL, client_seed TEXT NOT NULL, crash INTEGER NOT NULL,
                  auto INTEGER NOT NULL DEFAULT 0, started REAL NOT NULL,
                  status TEXT NOT NULL DEFAULT 'running', cashout INTEGER, payout INTEGER DEFAULT 0);
                CREATE INDEX IF NOT EXISTS idx_rounds_user_status ON rounds(user_id,status);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_running_round ON rounds(user_id) WHERE status='running';
                CREATE TABLE IF NOT EXISTS crash_rooms(
                  id TEXT PRIMARY KEY, seed TEXT NOT NULL, message TEXT NOT NULL,
                  crash INTEGER NOT NULL CHECK(crash BETWEEN 100 AND 10000),
                  starts_at REAL NOT NULL, created REAL NOT NULL,
                  status TEXT NOT NULL DEFAULT 'waiting' CHECK(status IN ('waiting','running','crashed')));
                CREATE UNIQUE INDEX IF NOT EXISTS idx_one_live_crash_room
                  ON crash_rooms((1)) WHERE status IN ('waiting','running');
                CREATE TABLE IF NOT EXISTS crash_bets(
                  id TEXT PRIMARY KEY, round_id TEXT NOT NULL REFERENCES crash_rooms(id),
                  user_id INTEGER NOT NULL REFERENCES users(id), stake INTEGER NOT NULL CHECK(stake>0),
                  stake_item_id INTEGER REFERENCES inventory(id),
                  currency TEXT NOT NULL CHECK(currency IN ('stars','grams')),
                  auto INTEGER NOT NULL DEFAULT 0 CHECK(auto=0 OR auto BETWEEN 105 AND 10000),
                  status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','active','cashed_out','lost')),
                  cashout INTEGER NOT NULL DEFAULT 0, payout INTEGER NOT NULL DEFAULT 0 CHECK(payout>=0),
                  created REAL NOT NULL, settled REAL, UNIQUE(round_id,user_id));
                CREATE INDEX IF NOT EXISTS idx_crash_bets_room ON crash_bets(round_id,created);
                CREATE INDEX IF NOT EXISTS idx_crash_bets_user ON crash_bets(user_id,created DESC);
                CREATE TABLE IF NOT EXISTS admin_audit(
                  id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER NOT NULL,
                  target_id INTEGER, action TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS bot_state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS star_orders(
                  id TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),
                  request_key TEXT NOT NULL,payload TEXT NOT NULL UNIQUE,
                  xtr INTEGER NOT NULL CHECK(xtr BETWEEN 1 AND 100),
                  target_currency TEXT NOT NULL DEFAULT 'stars' CHECK(target_currency IN ('stars','grams')),
                  credit_units INTEGER NOT NULL DEFAULT 0,
                  invoice_url TEXT,status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','checkout','paid','refunded')),
                  charge_id TEXT UNIQUE,created REAL NOT NULL,paid_at REAL,
                  UNIQUE(user_id,request_key));
            """)
            db.execute("INSERT OR IGNORE INTO promos(code,reward,max_uses) VALUES('CLEZZY50',5000,100000)")
            columns={r[1] for r in db.execute('PRAGMA table_info(inventory)')}
            for name,definition in [('collection_id','TEXT'),('attributes',"TEXT NOT NULL DEFAULT '{}'"),
                                    ('acquisition_currency',"TEXT NOT NULL DEFAULT 'stars'")]:
                if name not in columns:db.execute(f'ALTER TABLE inventory ADD COLUMN {name} {definition}')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_collection_edition ON inventory(collection_id,number) WHERE collection_id IS NOT NULL')
            for row in db.execute('SELECT id,gift_id FROM inventory WHERE collection_id IS NULL').fetchall():
                gift=self.gifts.get(row[1],{})
                if gift.get('collectible') and gift.get('collection_id') in self.collections:
                    attributes,number=self.collectible_attributes(db,gift['collection_id'])
                    db.execute('UPDATE inventory SET collection_id=?,number=?,attributes=? WHERE id=?',(gift['collection_id'],number,json.dumps(attributes),row[0]))
            user_columns={r[1] for r in db.execute('PRAGMA table_info(users)')}
            if 'payment_debt' not in user_columns:
                db.execute('ALTER TABLE users ADD COLUMN payment_debt INTEGER NOT NULL DEFAULT 0 CHECK(payment_debt>=0)')
            crash_columns={r[1] for r in db.execute('PRAGMA table_info(crash_bets)')}
            if 'stake_item_id' not in crash_columns:
                db.execute('ALTER TABLE crash_bets ADD COLUMN stake_item_id INTEGER REFERENCES inventory(id)')
            if 'reward_item_id' not in crash_columns:
                db.execute('ALTER TABLE crash_bets ADD COLUMN reward_item_id INTEGER REFERENCES inventory(id)')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_crash_stake_item ON crash_bets(stake_item_id) WHERE stake_item_id IS NOT NULL')
            order_columns={r[1] for r in db.execute('PRAGMA table_info(star_orders)')}
            if 'target_currency' not in order_columns:db.execute("ALTER TABLE star_orders ADD COLUMN target_currency TEXT NOT NULL DEFAULT 'stars'")
            if 'credit_units' not in order_columns:db.execute('ALTER TABLE star_orders ADD COLUMN credit_units INTEGER NOT NULL DEFAULT 0')
            db.execute("UPDATE star_orders SET credit_units=xtr*10000 WHERE credit_units=0 AND target_currency='stars'")
            db.execute("PRAGMA optimize")

    def throttle(self, key, limit=180, interval=60):
        now = self.clock()
        with self.rate_lock:
            recent = [t for t in self.limits.get(key, []) if now - t < interval]
            if len(recent) >= limit:
                raise GameError("Слишком много запросов. Подождите немного.", 429)
            recent.append(now)
            self.limits[key] = recent
            if len(self.limits) > 10000:
                self.limits = {k: v for k, v in self.limits.items() if v and now - v[-1] < interval}

    def upsert_user(self, db, user, seed_inventory=False):
        uid = user["id"]
        exists = db.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone()
        name = str(user.get("first_name", "Игрок"))[:100]
        username = str(user.get("username", ""))[:64]
        photo = str(user.get("photo_url", ""))[:2048]
        if not photo.startswith("https://"):
            photo = ""
        if exists:
            db.execute("UPDATE users SET first_name=?,username=?,photo_url=? WHERE id=?", (name, username, photo, uid))
        else:
            db.execute("INSERT INTO users(id,first_name,username,photo_url,stars,grams,server_seed,created) VALUES(?,?,?,?,?,?,?,?)",
                       (uid, name, username, photo, 0, 0, secrets.token_hex(32), self.clock()))
        return uid

    def authenticate(self, payload: dict, existing_token=""):
        self.throttle("auth", limit=300)
        if payload.get("init_data"):
            user = validate_init_data(str(payload["init_data"]), self.bot_token)
        elif self.demo:
            if existing_token:
                try:
                    uid = self.session_user(existing_token)
                    with self.db() as db:
                        u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
                        user = {"id": uid, "first_name": u["first_name"], "username": u["username"], "photo_url": u["photo_url"]}
                except GameError:
                    user = {"id": secrets.randbelow(900000000) + 100000000, "first_name": "Демо-игрок", "username": ""}
            else:
                user = {"id": secrets.randbelow(900000000) + 100000000, "first_name": "Демо-игрок", "username": ""}
        else:
            raise GameError("Откройте приложение через Telegram", 401)
        with self.db(write=True) as db:
            uid = self.upsert_user(db, user, seed_inventory=True)
            token = secrets.token_urlsafe(32)
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), uid, self.clock() + 86400))
            db.execute("DELETE FROM sessions WHERE expires<?", (self.clock(),))
            state = self.state(db, uid)
        return {"token": token, "state": state}

    def session_user(self, token):
        if not token:
            raise GameError("Нужна авторизация", 401)
        with self.db() as db:
            row = db.execute("SELECT user_id FROM sessions WHERE token_hash=? AND expires>?",
                             (hashlib.sha256(token.encode()).hexdigest(), self.clock())).fetchone()
        if not row:
            raise GameError("Сессия истекла. Откройте приложение заново.", 401)
        return row[0]

    @staticmethod
    def weighted_attribute(values):
        values=[x for x in values if x.get('weight',0)>0 and not x.get('crafted')]
        total=sum(x['weight'] for x in values)
        if not total:raise GameError('В коллекции нет доступных вариантов',409)
        roll=secrets.randbelow(total)
        for value in values:
            roll-=value['weight']
            if roll<0:return value

    def collectible_attributes(self,db,collection_id):
        c=self.collections.get(collection_id)
        if not c or not c.get('number_max'):raise GameError('Коллекция временно недоступна',409)
        maximum=c['number_max'];used={r[0] for r in db.execute('SELECT number FROM inventory WHERE collection_id=?',(collection_id,))};used={n for n in used if n is not None and 1<=n<=maximum}
        if len(used)>=maximum:raise GameError('Свободные номера этой коллекции закончились. Средства не списаны.',409)
        number=secrets.randbelow(maximum-len(used))+1
        for taken in sorted(used):
            if taken<=number:number+=1
            else:break
        attributes={key:self.weighted_attribute(c[group])['id'] for key,group in [('model','models'),('backdrop','backdrops'),('symbol','symbols')]}
        attributes.update(source=c['source'],catalog_version=self.catalog['version'])
        return attributes,number

    def gift_value_stars(self, gift_id, attributes=None):
        """Game valuation; backdrop bonuses are configurable, not live Getgems quotes."""
        price = self.gifts[gift_id]['price']
        if not self.gifts[gift_id].get('collectible'):
            return price
        backdrop = (attributes or {}).get('backdrop')
        return (price * {'0': 115, '49': 125}.get(str(backdrop), 100) + 99) // 100

    def ordinary_crash_reward(self, target_stars, source_id):
        candidates = [g for g in self.gifts.values() if not g.get('collectible')
                      and g['id'] != source_id and g['price'] <= target_stars]
        if not candidates:
            raise GameError('Нет обычного подарка подходящей стоимости', 409)
        return max(candidates, key=lambda gift: (gift['price'], gift['id']))['id']

    def add_gift(self,db,uid,gift_id,currency='stars'):
        self.column(currency)
        if gift_id not in self.gifts:raise GameError('Подарок не найден',404)
        gift=self.gifts[gift_id];cid=gift.get('collection_id') if gift.get('collectible') else None
        attributes,number=self.collectible_attributes(db,cid) if cid else ({},None)
        row=db.execute('INSERT INTO inventory(user_id,gift_id,acquired,collection_id,number,attributes,acquisition_currency) VALUES(?,?,?,?,?,?,?)',(uid,gift_id,self.clock(),cid,number,json.dumps(attributes),currency))
        return self.item(db.execute('SELECT * FROM inventory WHERE id=?',(row.lastrowid,)).fetchone())

    def item(self,row):
        attributes=json.loads(row['attributes'])
        value_stars=self.gift_value_stars(row['gift_id'],attributes)
        currency=row['acquisition_currency']
        return {'id':row['id'],'gift_id':row['gift_id'],'number':row['number'],'collection_id':row['collection_id'],
                'attributes':attributes,'acquired':row['acquired'],'acquisition_currency':currency,
                'value_stars':value_stars,'value':value_stars if currency=='stars' else self.price_units(value_stars,'grams')/1000000,
                'virtual':True}

    def log(self, db, uid, kind, title, amount=0, currency="stars", details=None):
        db.execute("INSERT INTO events(user_id,kind,title,amount,currency,details,created) VALUES(?,?,?,?,?,?,?)",
                   (uid, kind, title, amount, currency, json.dumps(details or {}, ensure_ascii=False), self.clock()))

    def state(self, db, uid):
        self.settle_rounds(db, uid)
        crash = self.shared_crash(db, uid)
        row = dict(db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone())
        inv = [self.item(r) for r in db.execute("SELECT * FROM inventory WHERE user_id=? AND status='owned' ORDER BY id DESC", (uid,))]
        history = [dict(r) for r in db.execute("SELECT id,kind,title,amount,currency,created,details FROM events WHERE user_id=? ORDER BY id DESC LIMIT 80", (uid,))]
        for event in history:
            event["details"] = json.loads(event["details"])
            if event["details"].get("shared_crash"):
                room = db.execute("SELECT * FROM crash_rooms WHERE id=?", (event["details"]["round_id"],)).fetchone()
                if room and room["status"] == "crashed":
                    event["details"]["proof"] = self.crash_proof(room)
        rounds = list(db.execute("SELECT * FROM rounds WHERE user_id=? ORDER BY started DESC LIMIT 15", (uid,)))
        return {"user": {"id": uid, "first_name": row["first_name"], "username": row["username"], "photo_url": row["photo_url"]},
                "balance": {"stars": row["stars"] / 100, "grams": row["grams"] / 1000000, "payment_debt_stars": row['payment_debt']/100},
                "inventory": inv, "history": history, "admin": uid in self.admin_ids,
                "demo": self.demo, "payments_enabled": self.payments_enabled, "virtual_economy": True,
                "stats": {"upgrades": row["upgrades"], "cases": row["cases_opened"], "inventory_value": sum(i['value_stars'] for i in inv)},
                "referral": {"code": row["referral_code"], "invited": db.execute("SELECT COUNT(*) FROM users WHERE referrer=?", (uid,)).fetchone()[0], "earned": row["referral_earned"] / 100},
                "fairness": {"commitment": hashlib.sha256(row["server_seed"].encode()).hexdigest(), "nonce": row["nonce"]},
                "crash": crash,
                "round": self.public_round(rounds[0]) if rounds else None,
                "rounds": [self.public_round(r) for r in rounds if r["status"] != "running"]}

    def column(self, currency):
        if currency not in {"stars", "grams"}:
            raise GameError("Неизвестная валюта")
        return currency

    def price_units(self, stars_price, currency):
        self.column(currency)
        return stars_price * 100 if currency == "stars" else int((Decimal(stars_price) * 1000000 / self.rate).to_integral_value(rounding=ROUND_UP))

    def debit(self, db, uid, units, currency):
        col = self.column(currency)
        if db.execute('SELECT payment_debt FROM users WHERE id=?',(uid,)).fetchone()[0]:
            raise GameError('Баланс ожидает урегулирования возврата платежа',409)
        if units < 1:
            raise GameError("Недопустимое списание")
        row = db.execute(f"UPDATE users SET {col}={col}-? WHERE id=? AND {col}>=?", (units, uid, units))
        if row.rowcount != 1:
            raise GameError("Недостаточно средств", 409)

    def credit(self, db, uid, units, currency):
        col = self.column(currency)
        if col=='stars':
            debt=db.execute('SELECT payment_debt FROM users WHERE id=?',(uid,)).fetchone()[0]
            if debt:
                repaid=min(units,debt)
                db.execute('UPDATE users SET payment_debt=payment_debt-? WHERE id=?',(repaid,uid))
                units-=repaid
        db.execute(f"UPDATE users SET {col}={col}+? WHERE id=?", (units, uid))

    def create_star_invoice(self, uid, amount, key, target_currency='stars'):
        if not self.payments_enabled:raise GameError('Оплата Telegram Stars не настроена',503)
        xtr=integer(amount,1,100)
        target_currency=self.column(target_currency)
        credit_units=xtr*10000 if target_currency=='stars' else int((Decimal(xtr*100)*1000000/self.rate).to_integral_value(rounding=ROUND_DOWN))
        if not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',key or ''):
            raise GameError('Нужен ключ запроса')
        with self.db(write=True) as db:
            row=db.execute('SELECT * FROM star_orders WHERE user_id=? AND request_key=?',(uid,key)).fetchone()
            if row and (row['xtr']!=xtr or row['target_currency']!=target_currency):raise GameError('Ключ платежа использован с другой суммой или валютой',409)
            if not row:
                oid=secrets.token_hex(16);payload='clezzy-starpay:'+oid
                db.execute('INSERT INTO star_orders(id,user_id,request_key,xtr,payload,created,target_currency,credit_units) VALUES(?,?,?,?,?,?,?,?)',
                           (oid,uid,key,xtr,payload,self.clock(),target_currency,credit_units))
                row=db.execute('SELECT * FROM star_orders WHERE id=?',(oid,)).fetchone()
            if row['invoice_url'] or row['status']!='pending':
                return {'order_id':row['id'],'status':row['status'],'invoice_url':row['invoice_url'],'target_currency':row['target_currency'],'credit':row['credit_units']/(100 if row['target_currency']=='stars' else 1000000)}
        url=telegram_api(self.bot_token,'createInvoiceLink',{
            'title':'OtonGifts · игровой баланс',
            'description':f'{credit_units/(100 if target_currency=="stars" else 1000000):g} игровых {"Stars" if target_currency=="stars" else "GRAM"} за {xtr} Telegram Stars.',
            'payload':row['payload'],'currency':'XTR',
            'prices':[{'label':'Игровые Stars','amount':xtr}],
        })
        if not isinstance(url,str) or not url.startswith('https://t.me/'):
            raise GameError('Не удалось создать счёт Telegram',502)
        with self.db(write=True) as db:
            db.execute('UPDATE star_orders SET invoice_url=? WHERE id=? AND invoice_url IS NULL',(url,row['id']))
            saved=db.execute('SELECT * FROM star_orders WHERE id=?',(row['id'],)).fetchone()
            return {'order_id':saved['id'],'status':saved['status'],'invoice_url':saved['invoice_url'],'target_currency':saved['target_currency'],'credit':saved['credit_units']/(100 if saved['target_currency']=='stars' else 1000000)}

    def payment_status(self,uid,oid):
        with self.db() as db:
            row=db.execute('SELECT id,status,xtr,target_currency,credit_units FROM star_orders WHERE id=? AND user_id=?',(oid,uid)).fetchone()
        if not row:raise GameError('Платёж не найден',404)
        return dict(row)

    def handle_payment_update(self,update):
        """Only Bot API getUpdates calls this. Browser requests cannot confirm invoices."""
        if not self.payments_enabled:return
        query=update.get('pre_checkout_query')
        if query:
            with self.db(write=True) as db:
                row=db.execute('SELECT * FROM star_orders WHERE payload=?',(query.get('invoice_payload'),)).fetchone()
                valid=bool(row and row['status']=='pending' and query.get('currency')=='XTR'
                    and type(query.get('total_amount')) is int and query['total_amount']==row['xtr']
                    and query.get('from',{}).get('id')==row['user_id'])
                if valid:db.execute('UPDATE star_orders SET status="checkout" WHERE id=?',(row['id'],))
            telegram_api(self.bot_token,'answerPreCheckoutQuery',{
                'pre_checkout_query_id':query['id'],'ok':valid,
                **({} if valid else {'error_message':'Счёт не найден или сумма изменилась.'})},timeout=8)
            return
        message=update.get('message') or {}
        paid=message.get('successful_payment')
        if paid:
            charge=paid.get('telegram_payment_charge_id');payload=paid.get('invoice_payload')
            if not isinstance(charge,str) or not 0<len(charge)<=256:return
            with self.db(write=True) as db:
                row=db.execute('SELECT * FROM star_orders WHERE payload=?',(payload,)).fetchone()
                if not row or row['user_id']!=message.get('from',{}).get('id') or paid.get('currency')!='XTR' or type(paid.get('total_amount')) is not int or paid['total_amount']!=row['xtr']:
                    LOG.warning('Ignoring unmatched payment receipt');return
                if row['status']=='paid' and row['charge_id']==charge:return
                if row['status'] not in ('pending','checkout') or db.execute('SELECT id FROM star_orders WHERE charge_id=?',(charge,)).fetchone():return
                db.execute('UPDATE star_orders SET status="paid",charge_id=?,paid_at=? WHERE id=?',(charge,self.clock(),row['id']))
                self.credit(db,row['user_id'],row['credit_units'],row['target_currency'])
                self.log(db,row['user_id'],'topup','Подтверждённый платёж Telegram',row['credit_units']/(100 if row['target_currency']=='stars' else 1000000),row['target_currency'],
                         {'order_id':row['id'],'xtr':row['xtr'],'charge_id':charge})
            return
        refunded=message.get('refunded_payment')
        if refunded and refunded.get('telegram_payment_charge_id'):
            with self.db(write=True) as db:
                row=db.execute('SELECT * FROM star_orders WHERE charge_id=? AND status="paid"',
                               (refunded['telegram_payment_charge_id'],)).fetchone()
                if not row:return
                units=row['credit_units'];currency=row['target_currency']
                balance=db.execute(f'SELECT {currency} FROM users WHERE id=?',(row['user_id'],)).fetchone()[0]
                missing=max(0,units-balance)
                debt=missing if currency=='stars' else int((Decimal(missing)*self.rate*100/1000000).to_integral_value(rounding=ROUND_UP))
                db.execute(f'UPDATE users SET {currency}={currency}-?,payment_debt=payment_debt+? WHERE id=?',
                           (min(balance,units),debt,row['user_id']))
                db.execute('UPDATE star_orders SET status="refunded" WHERE id=?',(row['id'],))
                self.log(db,row['user_id'],'refund','Возврат Telegram Stars',-units/(100 if currency=='stars' else 1000000),currency,
                         {'order_id':row['id'],'charge_id':row['charge_id']})

    def owned(self, db, uid, iid):
        row = db.execute("SELECT * FROM inventory WHERE id=? AND user_id=? AND status='owned'", (integer(iid, 1, 10**12), uid)).fetchone()
        if not row:
            raise GameError("Подарок отсутствует в вашем инвентаре", 404)
        return row

    def fair_roll(self, db, uid, action, client_seed="clezzy"):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", str(client_seed)):
            raise GameError("Недопустимый client seed")
        row = db.execute("SELECT server_seed,nonce FROM users WHERE id=?", (uid,)).fetchone()
        seed, nonce = row["server_seed"], row["nonce"]
        message = f"{uid}:{nonce}:{action}:{client_seed}"
        digest = hmac.new(seed.encode(), message.encode(), hashlib.sha256).hexdigest()
        roll = int(digest, 16) % 10000
        proof = {"server_seed": seed, "commitment": hashlib.sha256(seed.encode()).hexdigest(),
                 "nonce": nonce, "message": message, "digest": digest, "roll": roll, "algorithm": "HMAC-SHA256 modulo 10000"}
        db.execute("UPDATE users SET server_seed=?,nonce=nonce+1 WHERE id=?", (secrets.token_hex(32), uid))
        return roll, proof

    def referral_margin(self, db, uid, margin_cents):
        row = db.execute("SELECT referrer FROM users WHERE id=?", (uid,)).fetchone()
        if row[0] and margin_cents > 0:
            reward = margin_cents // 4
            if reward:
                self.credit(db, row[0], reward, "stars")
                db.execute("UPDATE users SET referral_earned=referral_earned+? WHERE id=?", (reward, row[0]))
                self.log(db, row[0], "referral", "Реферальное начисление", reward / 100)

    def mutate(self, uid, path, payload, key):
        self.throttle(f"mutation:{uid}", limit=90)
        if not re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", key or ""):
            raise GameError("Для операции нужен Idempotency-Key")
        fingerprint = hashlib.sha256((path + json.dumps(payload, sort_keys=True)).encode()).hexdigest()
        with self.db(write=True) as db:
            previous = db.execute("SELECT * FROM requests WHERE user_id=? AND key=?", (uid, key)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise GameError("Ключ операции уже использован для другого запроса", 409)
                return json.loads(previous["response"])
            if db.execute('SELECT payment_debt FROM users WHERE id=?',(uid,)).fetchone()[0]:
                raise GameError('Баланс ожидает урегулирования возврата платежа',409)
            result = self.action(db, uid, path, payload)
            result["state"] = self.state(db, uid)
            db.execute("INSERT INTO requests VALUES(?,?,?,?,?)", (uid, key, fingerprint, json.dumps(result, ensure_ascii=False), self.clock()))
            return result

    def action(self, db, uid, path, p):
        if path == "/api/cases/open":
            case = self.cases.get(p.get("case_id"))
            if not case:
                raise GameError("Кейс не найден", 404)
            if any(x.get('type')!='currency' and self.gifts[x['gift_id']].get('collectible') for x in case['loot']):
                raise GameError("Кейс содержит недопустимый коллекционный приз", 409)
            currency = self.column(p.get("currency", "stars"))
            self.debit(db, uid, self.price_units(case["price"], currency), currency)
            roll, proof = self.fair_roll(db, uid, "case:" + case["id"], p.get("client_seed", "clezzy"))
            cumulative = 0
            gift=None;reward=None
            for loot in case["loot"]:
                cumulative += loot["weight"]
                if roll < cumulative:
                    if loot.get('type')=='currency':
                        units=self.price_units(loot['amount_stars'],currency)
                        self.credit(db,uid,units,currency)
                        reward={'currency':currency,'amount':units/(100 if currency=='stars' else 1000000)}
                        self.log(db,uid,'case_reward','Приз на баланс',reward['amount'],currency,details={'case_id':case['id'],'proof':proof})
                    else:gift = self.add_gift(db, uid, loot["gift_id"], currency)
                    break
            db.execute("UPDATE users SET cases_opened=cases_opened+1 WHERE id=?", (uid,))
            self.log(db, uid, "case", case["name"], -self.price_units(case["price"],currency)/(100 if currency=='stars' else 1000000), currency, details={"gift_id": gift['gift_id'] if gift else None, "gift":gift, "reward":reward,"proof": proof})
            ev = sum((x['amount_stars'] if x.get('type')=='currency' else self.gifts[x['gift_id']]['price'])*x['weight'] for x in case['loot'])/10000
            self.referral_margin(db, uid, int((case["price"] - ev) * 100))
            return {"gift": gift, "reward":reward, "proof": proof}

        if path == "/api/inventory/upgrade":
            row=self.owned(db,uid,p.get('item_id'));gift=self.gifts[row['gift_id']];target=gift.get('upgrade_to')
            if not target:raise GameError('Этот подарок нельзя улучшить')
            cid=gift['collection_id'];attributes,number=self.collectible_attributes(db,cid);cost=self.catalog['upgrade_cost']
            self.debit(db,uid,cost*100,'stars')
            db.execute('UPDATE inventory SET gift_id=?,number=?,collection_id=?,attributes=? WHERE id=?',(target,number,cid,json.dumps(attributes),row['id']))
            db.execute('UPDATE users SET upgrades=upgrades+1 WHERE id=?',(uid,))
            item=self.item(db.execute('SELECT * FROM inventory WHERE id=?',(row['id'],)).fetchone())
            self.log(db,uid,'collectible','Улучшение '+gift['name'],-cost,details={'gift_id':target,'gift':item})
            return {'gift':item}

        if path == '/api/inventory/transfer':
            row=self.owned(db,uid,p.get('item_id'));recipient=integer(p.get('recipient_id'),1,2**63-1)
            if recipient==uid:raise GameError('Выберите другого игрока')
            if not db.execute('SELECT id FROM users WHERE id=?',(recipient,)).fetchone():raise GameError('Получатель ещё не зарегистрирован',404)
            db.execute('UPDATE inventory SET user_id=? WHERE id=?',(recipient,row['id']))
            item=self.item(db.execute('SELECT * FROM inventory WHERE id=?',(row['id'],)).fetchone())
            self.log(db,uid,'transfer','Подарок передан',details={'gift':item,'recipient_id':recipient})
            self.log(db,recipient,'transfer','Получен подарок',details={'gift':item,'sender_id':uid})
            return {'gift':item,'transferred':True,'recipient_id':recipient}

        if path == "/api/inventory/sell":
            ids = p.get("item_ids")
            if not isinstance(ids, list) or not 1 <= len(ids) <= 500 or len({str(i) for i in ids}) != len(ids):
                raise GameError("Выберите от 1 до 500 разных подарков")
            currency = self.column(p.get("currency", "stars"))
            value = 0
            for iid in ids:
                row = self.owned(db, uid, iid)
                value += self.gift_value_stars(row['gift_id'],json.loads(row['attributes']))
                db.execute("UPDATE inventory SET status='sold' WHERE id=?", (row["id"],))
            units = self.price_units(value, currency)
            self.credit(db, uid, units, currency)
            self.log(db, uid, "sell", f"Продажа подарков · {len(ids)} шт.", units / (100 if currency == "stars" else 1000000), currency)
            return {"sold": len(ids), "value": value}

        if path == "/api/shop/buy":
            gid = p.get("gift_id")
            gift = self.gifts.get(gid)
            if not gift:
                raise GameError("Подарок не найден", 404)
            if gift.get("collectible"):
                raise GameError("Коллекционный подарок можно получить через улучшение", 409)
            currency=self.column(p.get('currency','stars'))
            units=self.price_units(gift['price'],currency)
            self.debit(db, uid, units, currency)
            item = self.add_gift(db, uid, gid, currency)
            self.log(db, uid, "buy", "Покупка " + gift["name"], -units/(100 if currency=='stars' else 1000000),currency,details={"gift":item})
            return {"gift": item}

        if path == "/api/upgrades/play":
            row = self.owned(db, uid, p.get("item_id"))
            source = self.gifts[row["gift_id"]]
            target = self.gifts.get(p.get("target_id"))
            if target and target.get('collectible'):
                raise GameError('Целью может быть только обычный подарок',409)
            source_value=self.gift_value_stars(row['gift_id'],json.loads(row['attributes']))
            if not target or target["price"] <= source_value:
                raise GameError("Выберите подарок дороже исходного")
            chance = min(9500, int(Decimal(source_value) * 9000 / target["price"]))
            roll, proof = self.fair_roll(db, uid, f"upgrade:{row['id']}:{target['id']}", p.get("client_seed", "clezzy"))
            win = roll < chance
            db.execute("UPDATE inventory SET status='used' WHERE id=?", (row["id"],))
            result = self.add_gift(db, uid, target["id"], row['acquisition_currency']) if win else None
            db.execute("UPDATE users SET upgrades=upgrades+1 WHERE id=?", (uid,))
            self.log(db, uid, "upgrade", ("Успешный апгрейд · " if win else "Неудачный апгрейд · ") + target["name"],
                     target["price"] - source["price"] if win else -source["price"], details={"proof": proof, "chance": chance / 100, "gift_id": target["id"], "win": win, "gift":result})
            self.referral_margin(db, uid, source["price"] * 10)
            return {"win": win, "gift": result, "chance": chance / 100, "proof": proof}

        if path == "/api/crash/bet":
            room = self.advance_crash(db)
            if p.get("round_id") != room["id"] or room["status"] != "waiting":
                raise GameError("Приём ставок завершён. Дождитесь следующего раунда.", 409)
            if db.execute("SELECT id FROM crash_bets WHERE round_id=? AND user_id=?", (room["id"], uid)).fetchone():
                raise GameError("Ваша ставка уже принята в этом раунде", 409)
            stake_item_id = None
            if p.get('currency') == 'nft':
                item = self.owned(db, uid, p.get('item_id'))
                gift = self.gifts[item['gift_id']]
                if gift.get('collectible') and (not item['collection_id'] or item['number'] is None):
                    raise GameError('Коллекционный подарок не имеет номера', 409)
                stake_item_id, currency = item['id'], item['acquisition_currency']
                scale = 100 if currency == 'stars' else 1000000
                stake = self.price_units(self.gift_value_stars(item['gift_id'],json.loads(item['attributes'])),currency)
            else:
                currency = self.column(p.get("currency", "stars"))
                scale = 100 if currency == "stars" else 1000000
                stake = amount_units(p.get("stake"), scale, 10000 if currency == "stars" else 80)
                if stake < (1000 if currency == "stars" else 80000):
                    raise GameError("Минимальная ставка: 10 Stars или 0.08 GRAM")
            auto_input = p.get("auto", 0)
            auto = 0 if auto_input in (0, "0", None, "") else amount_units(auto_input, 100, 100)
            if auto and auto < 105:
                raise GameError("Автовывод: от 1.05x до 100x")
            if stake_item_id is None:
                self.debit(db, uid, stake, currency)
            elif db.execute("UPDATE inventory SET status='in_crash' WHERE id=? AND user_id=? AND status='owned'",
                            (stake_item_id, uid)).rowcount != 1:
                raise GameError('Подарок уже участвует в другой операции', 409)
            bid = secrets.token_hex(12)
            db.execute("INSERT INTO crash_bets(id,round_id,user_id,stake,currency,auto,created,stake_item_id) VALUES(?,?,?,?,?,?,?,?)",
                       (bid, room["id"], uid, stake, currency, auto, self.clock(), stake_item_id))
            if stake_item_id is None:
                self.log(db, uid, "crash_bet", "Ставка в общий Crash", -stake / scale, currency,
                         {"round_id": room["id"], "bet_id": bid, "shared_crash": True})
                self.referral_margin(db, uid, round(stake / scale * (1 if currency == "stars" else self.rate) * 3))
            else:
                self.log(db, uid, 'crash_bet', 'NFT ставка · ' + gift['name'], -1, 'nft',
                         {'round_id': room['id'], 'bet_id': bid, 'shared_crash': True, 'gift': self.item(item),
                          'value_stars': self.gift_value_stars(item['gift_id'],json.loads(item['attributes']))})
            bet = self.crash_bet_row(db, bid)
            return {"bet": self.public_bet(bet)}

        if path == "/api/crash/collect":
            accepted_at = self.clock()
            self.advance_crash(db, accepted_at)
            bet = db.execute("SELECT * FROM crash_bets WHERE id=? AND user_id=?", (str(p.get("bet_id", "")), uid)).fetchone()
            if not bet:
                raise GameError("Ставка не найдена", 404)
            room = db.execute("SELECT * FROM crash_rooms WHERE id=?", (bet["round_id"],)).fetchone()
            if bet["status"] == "queued":
                raise GameError("Раунд ещё не начался", 409)
            if bet["status"] == "active":
                self.finish_shared_bet(db, bet, "cashed_out", self.crash_multiplier(room, accepted_at))
            bet = self.crash_bet_row(db, bet['id'])
            return {"bet": self.public_bet(bet)}

        # Compatibility routes for saved personal rounds from versions 1–2.
        if path == "/api/crash/start":
            self.settle_rounds(db, uid)
            if db.execute("SELECT id FROM rounds WHERE user_id=? AND status='running'", (uid,)).fetchone():
                raise GameError("Сначала завершите текущий раунд", 409)
            currency = self.column(p.get("currency", "stars"))
            scale = 100 if currency == "stars" else 1000000
            stake = amount_units(p.get("stake"), scale, 10000 if currency == "stars" else 80)
            if stake < (1000 if currency == "stars" else 80000):
                raise GameError("Минимальная ставка: 10 Stars или 0.08 GRAM")
            auto_input = p.get("auto", 0)
            auto = 0 if auto_input in (0, "0", None, "") else amount_units(auto_input, 100, 100)
            if auto and auto < 105:
                raise GameError("Автовывод: от 1.05x до 100x")
            # Published in state BEFORE stake. Each round reveals seed only after settling.
            user = db.execute("SELECT server_seed,nonce FROM users WHERE id=?", (uid,)).fetchone()
            seed = user["server_seed"]
            client = str(p.get("client_seed", "clezzy"))
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", client):
                raise GameError("Недопустимый client seed")
            message = f"{uid}:{user['nonce']}:crash:{client}"
            digest = hmac.new(seed.encode(), message.encode(), hashlib.sha256).hexdigest()
            u = int(digest[:13], 16) / (2 ** 52)
            crash = min(10000, max(100, math.floor(97 / max(u, 1 / 2 ** 52))))
            self.debit(db, uid, stake, currency)
            rid = secrets.token_hex(12)
            db.execute("INSERT INTO rounds(id,user_id,stake,currency,seed,client_seed,crash,auto,started) VALUES(?,?,?,?,?,?,?,?,?)",
                       (rid, uid, stake, currency, seed, message, crash, auto, self.clock()))
            db.execute("UPDATE users SET server_seed=?,nonce=nonce+1 WHERE id=?", (secrets.token_hex(32), uid))
            self.log(db, uid, "crash_bet", "Ставка в Crash", -stake / scale, currency)
            self.referral_margin(db, uid, round(stake / scale * (1 if currency == "stars" else self.rate) * 3))
            return {"round": self.public_round(db.execute("SELECT * FROM rounds WHERE id=?", (rid,)).fetchone())}

        if path == "/api/crash/cashout":
            self.settle_rounds(db, uid)
            row = db.execute("SELECT * FROM rounds WHERE id=? AND user_id=?", (str(p.get("round_id", "")), uid)).fetchone()
            if not row:
                raise GameError("Раунд не найден", 404)
            if row["status"] == "running":
                self.finish_round(db, row, "cashed_out", self.multiplier(row))
                row = db.execute("SELECT * FROM rounds WHERE id=?", (row["id"],)).fetchone()
            return {"round": self.public_round(row)}

        if path == "/api/promo/redeem":
            code = str(p.get("code", "")).strip().upper()
            if code == "/CLEZZYKRYT" or code == "CLEZZYKRYT":
                if uid not in self.admin_ids:
                    raise GameError("Доступ только для администратора", 403)
                return {"open_admin": True}
            promo = db.execute("SELECT * FROM promos WHERE code=?", (code,)).fetchone()
            if not promo or promo["uses"] >= promo["max_uses"] or (promo["expires"] and promo["expires"] < self.clock()):
                raise GameError("Промокод недействителен")
            if db.execute("SELECT 1 FROM redemptions WHERE code=? AND user_id=?", (code, uid)).fetchone():
                raise GameError("Этот промокод уже активирован", 409)
            if promo["owner"] == uid:
                raise GameError("Нельзя активировать собственный код")
            db.execute("INSERT INTO redemptions VALUES(?,?,?)", (code, uid, self.clock()))
            db.execute("UPDATE promos SET uses=uses+1 WHERE code=?", (code,))
            self.credit(db, uid, promo["reward"], "stars")
            self.log(db, uid, "promo", "Промокод " + code, promo["reward"] / 100)
            if promo["owner"]:
                db.execute("UPDATE users SET referrer=? WHERE id=? AND referrer IS NULL", (promo["owner"], uid))
            return {"reward": promo["reward"] / 100}

        if path == "/api/referrals/create":
            existing = db.execute("SELECT referral_code FROM users WHERE id=?", (uid,)).fetchone()[0]
            if existing:
                return {"code": existing}
            code = str(p.get("code", "")).strip().upper()
            if not re.fullmatch(r"[A-Z0-9_]{4,20}", code) or code == "CLEZZYKRYT":
                raise GameError("Код: 4–20 латинских букв, цифр или _")
            if db.execute("SELECT 1 FROM promos WHERE code=?", (code,)).fetchone():
                raise GameError("Этот код уже занят", 409)
            db.execute("INSERT INTO promos(code,reward,max_uses,owner) VALUES(?,500,100000,?)", (code, uid))
            db.execute("UPDATE users SET referral_code=? WHERE id=?", (code, uid))
            return {"code": code}

        if path == "/api/demo/topup":
            if not self.demo:
                raise GameError("Тестовое пополнение отключено", 403)
            currency = self.column(p.get("currency", "stars"))
            units = amount_units(p.get("amount"), 100 if currency == "stars" else 1000000, 10000 if currency == "stars" else 80)
            self.credit(db, uid, units, currency)
            self.log(db, uid, "topup", "Тестовое пополнение", units / (100 if currency == "stars" else 1000000), currency)
            return {"ok": True}

        if path.startswith("/api/admin/"):
            if uid not in self.admin_ids:
                raise GameError("Доступ только для администратора", 403)
            if path == "/api/admin/grant":
                target = integer(p.get("user_id"), 1, 2 ** 52)
                if not db.execute("SELECT id FROM users WHERE id=?", (target,)).fetchone():
                    raise GameError("Пользователь должен сначала открыть приложение", 404)
                reason = str(p.get("reason", "")).strip()[:250]
                if len(reason) < 3:
                    raise GameError("Укажите причину начисления")
                kind = p.get("kind")
                if kind == "gift":
                    qty = integer(p.get("quantity", 1), 1, 20)
                    gifts = [self.add_gift(db, target, p.get("gift_id")) for _ in range(qty)]
                    self.log(db, target, "admin", f"Подарки от администратора · {qty} шт.", details={"reason": reason})
                    result = {"gifts": gifts}
                else:
                    currency = self.column(kind)
                    units = amount_units(p.get("amount"), 100 if currency == "stars" else 1000000, 1000000)
                    self.credit(db, target, units, currency)
                    self.log(db, target, "admin", "Начисление от администратора", units / (100 if currency == "stars" else 1000000), currency, {"reason": reason})
                    result = {"granted": True}
                db.execute("INSERT INTO admin_audit(admin_id,target_id,action,payload,created) VALUES(?,?,?,?,?)",
                           (uid, target, "grant", json.dumps(p, ensure_ascii=False), self.clock()))
                return result
            if path == "/api/admin/promo":
                code = str(p.get("code", "")).strip().upper()
                if not re.fullmatch(r"[A-Z0-9_]{4,24}", code) or code == "CLEZZYKRYT":
                    raise GameError("Недопустимый промокод")
                if db.execute("SELECT code FROM promos WHERE code=?", (code,)).fetchone():
                    raise GameError("Промокод уже существует", 409)
                reward = amount_units(p.get("reward"), 100, 100000)
                uses = integer(p.get("max_uses", 100), 1, 1000000)
                db.execute("INSERT INTO promos(code,reward,max_uses) VALUES(?,?,?)", (code, reward, uses))
                db.execute("INSERT INTO admin_audit(admin_id,action,payload,created) VALUES(?,?,?,?)", (uid, "promo", json.dumps(p), self.clock()))
                return {"code": code}
        raise GameError("Операция не найдена", 404)

    @staticmethod
    def crash_point(seed, message):
        digest = hmac.new(seed.encode(), message.encode(), hashlib.sha256).hexdigest()
        u = int(digest[:13], 16) / 2 ** 52
        return min(10000, max(100, math.floor(97 / max(u, 1 / 2 ** 52))))

    def crash_multiplier(self, room, now=None):
        now = self.clock() if now is None else now
        elapsed = max(0, now - room["starts_at"])
        current = min(10000, math.floor(100 * math.exp(min(elapsed / 8, math.log(100)))))
        # Compare discrete transitions using the same absolute clock as the crash.
        # Subtracting large Unix timestamps can otherwise lose a cent at 1.25x.
        if current < 10000 and now >= room["starts_at"] + 8 * math.log((current + 1) / 100):
            current += 1
        if current > 100 and now < room["starts_at"] + 8 * math.log(current / 100):
            current -= 1
        return current

    @staticmethod
    def crash_proof(room):
        return {"server_seed": room["seed"], "message": room["message"],
                "commitment": hashlib.sha256(room["seed"].encode()).hexdigest(),
                "digest": hmac.new(room["seed"].encode(), room["message"].encode(), hashlib.sha256).hexdigest(),
                "crash": room["crash"] / 100, "algorithm": "HMAC-SHA256 first 52 bits; floor(97/u), bounded 1–100x"}

    def finish_shared_bet(self, db, bet, status, multiplier=0):
        """One guarded row update, its credit and its history event share the transaction."""
        payout = bet["stake"] * multiplier // 100 if status == "cashed_out" else 0
        changed = db.execute("UPDATE crash_bets SET status=?,cashout=?,payout=?,settled=? WHERE id=? AND status IN ('queued','active')",
                             (status, multiplier, payout, self.clock(), bet["id"]))
        if changed.rowcount != 1:
            return
        if bet['stake_item_id'] is not None:
            source=db.execute('SELECT gift_id,attributes FROM inventory WHERE id=?',(bet['stake_item_id'],)).fetchone()
            consumed = db.execute("UPDATE inventory SET status='used' WHERE id=? AND user_id=? AND status='in_crash'",
                                  (bet['stake_item_id'], bet['user_id']))
            if consumed.rowcount != 1:
                raise GameError('Не удалось завершить NFT ставку', 409)
            if payout:
                target_stars = self.gift_value_stars(source['gift_id'], json.loads(source['attributes'])) * multiplier // 100
                reward_id=self.ordinary_crash_reward(target_stars,source['gift_id'])
                reward=self.add_gift(db,bet['user_id'],reward_id,bet['currency'])
                payout=self.price_units(reward['value_stars'],bet['currency'])
                db.execute('UPDATE crash_bets SET payout=?,reward_item_id=? WHERE id=?',(payout,reward['id'],bet['id']))
            else:
                reward=None
        elif payout:
            self.credit(db, bet["user_id"], payout, bet["currency"])
        scale = 100 if bet["currency"] == "stars" else 1000000
        self.log(db, bet["user_id"], "crash", ("Crash · подарок за " if bet['stake_item_id'] else "Crash · забрано на ")+f"{multiplier / 100:.2f}x" if payout else "Crash · ставка сгорела",
                 payout / scale, bet["currency"], {"round_id": bet["round_id"], "bet_id": bet["id"],
                 "shared_crash": True, "cashout": multiplier / 100, "payout": payout / scale,
                 "stake_item_id": bet['stake_item_id'],"reward":reward if bet['stake_item_id'] is not None else None})

    def advance_crash(self, db, now=None):
        """Lazy global clock: every client sees the same round; offline auto bets also settle.

        Call only within a write transaction. A round's seed is private until its crash,
        including after any individual player's manual/automatic cashout.
        """
        now = self.clock() if now is None else now
        room = db.execute("SELECT * FROM crash_rooms ORDER BY created DESC,rowid DESC LIMIT 1").fetchone()
        if room and room["status"] != "crashed" and now >= room["starts_at"]:
            db.execute("UPDATE crash_rooms SET status='running' WHERE id=? AND status='waiting'", (room["id"],))
            db.execute("UPDATE crash_bets SET status='active' WHERE round_id=? AND status='queued'", (room["id"],))
            crashed = now >= room["starts_at"] + 8 * math.log(room["crash"] / 100)
            current = self.crash_multiplier(room, now)
            bets = db.execute("SELECT * FROM crash_bets WHERE round_id=? AND status='active'", (room["id"],)).fetchall()
            for bet in bets:
                # Event order matters when the server was idle for the entire flight.
                if bet["auto"] and bet["auto"] < room["crash"] and current >= bet["auto"]:
                    self.finish_shared_bet(db, bet, "cashed_out", bet["auto"])
                elif crashed:
                    self.finish_shared_bet(db, bet, "lost")
            if crashed:
                db.execute("UPDATE crash_rooms SET status='crashed' WHERE id=?", (room["id"],))
            room = db.execute("SELECT * FROM crash_rooms WHERE id=?", (room["id"],)).fetchone()
        if not room or (room["status"] == "crashed" and now >= room["starts_at"] + 8 * math.log(room["crash"] / 100) + 3):
            rid, seed = secrets.token_hex(12), secrets.token_hex(32)
            message = "clezzy-shared-crash:" + rid
            point = self.crash_point(seed, message)
            db.execute("INSERT INTO crash_rooms(id,seed,message,crash,starts_at,created) VALUES(?,?,?,?,?,?)",
                       (rid, seed, message, point, now + 6, now))
            room = db.execute("SELECT * FROM crash_rooms WHERE id=?", (rid,)).fetchone()
        return room

    def crash_bet_row(self, db, bid):
        return db.execute("""SELECT b.*,u.first_name,u.photo_url,i.gift_id AS stake_gift_id,
                          i.number AS stake_number,i.collection_id AS stake_collection_id,
                          i.attributes AS stake_attributes, i.acquisition_currency AS stake_currency,
                          ri.gift_id AS reward_gift_id,ri.id AS reward_inventory_id FROM crash_bets b
                          JOIN users u ON u.id=b.user_id LEFT JOIN inventory i ON i.id=b.stake_item_id
                          LEFT JOIN inventory ri ON ri.id=b.reward_item_id
                          WHERE b.id=?""", (bid,)).fetchone()

    def public_bet(self, bet):
        scale = 100 if bet["currency"] == "stars" else 1000000
        return {"id": bet["id"], "round_id": bet["round_id"],
                "user": {"id": bet["user_id"], "first_name": bet["first_name"], "photo_url": bet["photo_url"]},
                "stake": bet["stake"] / scale, "currency": bet["currency"], "auto": bet["auto"] / 100,
                "status": bet["status"], "cashout": bet["cashout"] / 100, "payout": bet["payout"] / scale,
                "reward_item": ({'id':bet['reward_inventory_id'],'gift_id':bet['reward_gift_id'],
                                 'name':self.gifts[bet['reward_gift_id']]['name'],
                                 'value':bet['payout']/scale,'currency':bet['currency']}
                                if bet['reward_inventory_id'] is not None else None),
                "stake_item": ({'id':bet['stake_item_id'], 'gift_id':bet['stake_gift_id'],
                                'name':self.gifts[bet['stake_gift_id']]['name'], 'number':bet['stake_number'],
                                'collection_id':bet['stake_collection_id'], 'attributes':json.loads(bet['stake_attributes']),
                                'acquisition_currency':bet['stake_currency'],
                                'virtual':True} if bet['stake_item_id'] is not None else None)}

    def room_bets(self, db, rid):
        rows = db.execute("""SELECT b.*,u.first_name,u.photo_url,i.gift_id AS stake_gift_id,
                           i.number AS stake_number,i.collection_id AS stake_collection_id,i.attributes AS stake_attributes,
                           i.acquisition_currency AS stake_currency,ri.gift_id AS reward_gift_id,
                           ri.id AS reward_inventory_id
                           FROM crash_bets b JOIN users u ON u.id=b.user_id
                           LEFT JOIN inventory i ON i.id=b.stake_item_id
                           LEFT JOIN inventory ri ON ri.id=b.reward_item_id WHERE b.round_id=?
                           ORDER BY CASE b.status WHEN 'cashed_out' THEN 0 ELSE 1 END,b.settled,b.created""", (rid,)).fetchall()
        return [self.public_bet(row) for row in rows]

    def shared_crash(self, db, uid):
        now = self.clock()
        room = self.advance_crash(db, now)
        bets = self.room_bets(db, room["id"])
        previous = db.execute("SELECT * FROM crash_rooms WHERE status='crashed' AND id!=? ORDER BY created DESC,rowid DESC LIMIT 15", (room["id"],)).fetchall()
        result = {"id": room["id"], "phase": room["status"], "starts_at": room["starts_at"],
                  "server_time": now, "waiting_seconds": 6,
                  "multiplier": (room["crash"] if room["status"] == "crashed" else self.crash_multiplier(room, now)) / 100,
                  "commitment": hashlib.sha256(room["seed"].encode()).hexdigest(),
                  "bets": bets, "players_count": len(bets), "mine": next((b for b in bets if b["user"]["id"] == uid), None),
                  "previous": [{"id": r["id"], "multiplier": r["crash"] / 100, "proof": self.crash_proof(r)} for r in previous]}
        if room["status"] == "crashed":
            result["proof"] = self.crash_proof(room)
        if previous:
            last = previous[0]
            result["last_round"] = {"id": last["id"], "multiplier": last["crash"] / 100, "bets": self.room_bets(db, last["id"]), "proof": self.crash_proof(last)}
        return result

    def multiplier(self, row):
        elapsed = max(0, self.clock() - row["started"])
        return min(10000, math.floor(100 * math.exp(min(elapsed / 8, math.log(100)))))

    def finish_round(self, db, row, status, multiplier=0):
        payout = row["stake"] * multiplier // 100 if status == "cashed_out" else 0
        updated = db.execute("UPDATE rounds SET status=?,cashout=?,payout=? WHERE id=? AND status='running'", (status, multiplier or None, payout, row["id"]))
        if updated.rowcount != 1:
            return
        if payout:
            self.credit(db, row["user_id"], payout, row["currency"])
        scale = 100 if row["currency"] == "stars" else 1000000
        self.log(db, row["user_id"], "crash", f"Crash · {multiplier / 100:.2f}x" if payout else f"Crash · сгорело на {row['crash'] / 100:.2f}x", payout / scale, row["currency"],
                 {"round_id": row["id"], "proof": {"server_seed": row["seed"], "commitment": hashlib.sha256(row["seed"].encode()).hexdigest(), "message": row["client_seed"]}})

    def settle_rounds(self, db, uid):
        row = db.execute("SELECT * FROM rounds WHERE user_id=? AND status='running'", (uid,)).fetchone()
        if not row:
            return
        current = self.multiplier(row)
        # Auto settlement uses event order, so closing the tab never skips an eligible auto cashout.
        if row["auto"] and row["auto"] < row["crash"] and current >= row["auto"]:
            self.finish_round(db, row, "cashed_out", row["auto"])
        elif current >= row["crash"]:
            self.finish_round(db, row, "crashed")

    def public_round(self, row):
        scale = 100 if row["currency"] == "stars" else 1000000
        r = {"id": row["id"], "status": row["status"], "stake": row["stake"] / scale,
             "currency": row["currency"], "started": row["started"], "server_time": self.clock(),
             "multiplier": (row["cashout"] or row["crash"]) / 100 if row["status"] != "running" else self.multiplier(row) / 100,
             "auto": row["auto"] / 100, "payout": row["payout"] / scale,
             "commitment": hashlib.sha256(row["seed"].encode()).hexdigest()}
        if row["status"] != "running":
            r["proof"] = {"server_seed": row["seed"], "commitment": r["commitment"], "message": row["client_seed"], "crash": row["crash"] / 100}
        return r

    def read(self, uid, path):
        self.throttle(f"read:{uid}", limit=600)
        if path.startswith('/api/payments/stars/order/'):
            return self.payment_status(uid,path.rsplit('/',1)[-1])
        if path in {"/api/me", "/api/crash/state", "/api/crash/room"}:
            with self.db(write=True) as db:
                return {"state": self.state(db, uid)}
        if path == "/api/admin/users":
            if uid not in self.admin_ids:
                raise GameError("Доступ только для администратора", 403)
            with self.db() as db:
                users = [dict(r) for r in db.execute("SELECT id,first_name,username,stars,grams FROM users ORDER BY created DESC LIMIT 100")]
                audit = [dict(r) for r in db.execute("SELECT id,admin_id,target_id,action,created FROM admin_audit ORDER BY id DESC LIMIT 50")]
                for user in users:
                    user["stars"] /= 100
                    user["grams"] /= 1000000
            return {"users": users, "audit": audit}
        raise GameError("Страница не найдена", 404)

    def bot_loop(self, stop_event):
        with self.db() as db:
            row = db.execute("SELECT value FROM bot_state WHERE key='offset'").fetchone()
        offset = int(row[0]) if row else 0
        mini_url = os.environ.get("MINI_APP_URL", "")
        if not mini_url.startswith("https://"):
            LOG.warning("Bot polling needs an HTTPS MINI_APP_URL; polling disabled")
            return
        while not stop_event.is_set():
            try:
                updates = telegram_api(self.bot_token, "getUpdates", {"offset": offset, "timeout": 25, "allowed_updates": ["message","pre_checkout_query"]})
                for update in updates:
                    self.handle_payment_update(update)
                    message = update.get("message", {})
                    sender = message.get("from", {})
                    text = message.get("text", "").split("@")[0].split(" ")[0]
                    if message.get('chat',{}).get('type')=='private' and sender.get('id') and text in {'/terms','/paysupport'}:
                        value=os.environ.get('TERMS_URL','') if text=='/terms' else os.environ.get('SUPPORT_CONTACT','')
                        telegram_api(self.bot_token,'sendMessage',{'chat_id':sender['id'],
                            'text':('Условия: ' if text=='/terms' else 'Помощь по платежам: ')+(value or 'Свяжитесь с владельцем бота.')})
                    if message.get("chat", {}).get("type") == "private" and sender.get("id") and text in {"/start", "/ClezzyKryt", "/clezzykryt"}:
                        with self.db(write=True) as db:
                            self.upsert_user(db, sender)
                        admin = text.lower() == "/clezzykryt"
                        if admin and sender["id"] not in self.admin_ids:
                            telegram_api(self.bot_token, "sendMessage", {"chat_id": sender["id"], "text": "Доступ только для администратора."})
                        elif not admin:
                            send_welcome(self.bot_token, sender["id"], mini_url)
                        else:
                            url = mini_url.rstrip("/") + "/?view=admin"
                            telegram_api(self.bot_token, "sendMessage", {"chat_id": sender["id"],
                              "text": "Панель администратора OtonGifts",
                              "reply_markup": {"inline_keyboard": [[{"text": "Админ-панель", "web_app": {"url": url}}]]}})
                    offset = update["update_id"] + 1
                    with self.db(write=True) as db:
                        db.execute("INSERT OR REPLACE INTO bot_state VALUES('offset',?)", (str(offset),))
            except (GameError, sqlite3.Error):
                LOG.warning("Bot update processing failed; retrying without exposing credentials")
                stop_event.wait(3)


def handler_for(game: Game):
    class Handler(BaseHTTPRequestHandler):
        server_version = "OtonGifts/6.0"

        def log_message(self, format, *args):
            # Omit URLs/body/headers: Telegram init data and credentials are sensitive.
            LOG.info("HTTP %s %s", self.command, args[1] if len(args) > 1 else "")

        def write_headers(self, status, content_type, length, cors=False):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            self.send_header("Cache-Control", "no-store" if self.path.startswith("/api") else "no-cache")
            if cors:self.send_header('Access-Control-Allow-Origin','*')
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' https://telegram.org https://unpkg.com; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data: https:; connect-src 'self' https:; frame-src https:; object-src 'none'; base-uri 'self'")
            self.end_headers()

        def json_response(self, value, status=200,cors=False):
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
            self.write_headers(status, "application/json; charset=utf-8", len(body),cors)
            self.wfile.write(body)

        def body(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 32768:
                    raise GameError("Недопустимый размер запроса", 413)
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict):
                    raise GameError("Ожидается JSON-объект")
                return value
            except (ValueError, UnicodeDecodeError):
                raise GameError("Некорректный JSON") from None

        def token(self):
            value = self.headers.get("Authorization", "")
            return value[7:] if value.startswith("Bearer ") else ""

        def do_GET(self):
            path = urlsplit(self.path).path
            try:
                if path == "/api/health":
                    return self.json_response({"ok": True, "demo": game.demo, "virtual_economy": True})
                if path == "/catalog.json":
                    return self.json_response({**game.catalog, "bot_username": os.environ.get("BOT_USERNAME", "").lstrip("@")})
                if path=='/tonconnect-manifest.json':
                    app_url=os.environ.get('MINI_APP_URL','').strip()
                    if not app_url.startswith('https://'):raise GameError('Для кошелька нужен HTTPS MINI_APP_URL',503)
                    parsed=urlsplit(app_url);origin=f'{parsed.scheme}://{parsed.netloc}'
                    return self.json_response({'url':app_url,'name':'OtonGifts','iconUrl':origin+'/assets/icons/app-icon.png'},cors=True)
                if path.startswith("/api/"):
                    return self.json_response(game.read(game.session_user(self.token()), path))
                relative = unquote(path.lstrip("/") or "index.html")
                requested = PUBLIC / relative
                requested = requested.resolve()
                if not requested.is_relative_to(PUBLIC.resolve()) or relative.startswith("asset-packs/"):
                    raise GameError("Файл не найден", 404)
                try:
                    body = ASSETS.read(relative)
                except FileNotFoundError:
                    raise GameError("Файл не найден", 404) from None
                mime = mimetypes.guess_type(relative)[0] or "application/octet-stream"
                self.write_headers(200, mime + ("; charset=utf-8" if mime.startswith("text/") else ""), len(body))
                self.wfile.write(body)
            except GameError as e:
                self.json_response({"error": e.message}, e.status)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                LOG.exception("Request processing failed")
                self.json_response({"error": "Внутренняя ошибка сервера"}, 500)

        def do_POST(self):
            path = urlsplit(self.path).path
            try:
                origin = self.headers.get("Origin", "")
                if origin and urlsplit(origin).netloc != self.headers.get("Host", ""):
                    raise GameError("Недопустимый источник запроса", 403)
                p = self.body()
                if path == "/api/auth":
                    game.throttle("auth:" + self.client_address[0], limit=30)
                    return self.json_response(game.authenticate(p, self.token()))
                uid = game.session_user(self.token())
                if path=='/api/payments/stars/invoice':
                    game.throttle(f'invoice:{uid}',limit=12,interval=60)
                    return self.json_response(game.create_star_invoice(uid,p.get('amount_xtr'),self.headers.get('Idempotency-Key',''),p.get('target_currency','stars')))
                return self.json_response(game.mutate(uid, path, p, self.headers.get("Idempotency-Key", "")))
            except GameError as e:
                self.json_response({"error": e.message}, e.status)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                LOG.exception("Mutation processing failed")
                self.json_response({"error": "Внутренняя ошибка сервера"}, 500)
    return Handler


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    game = Game()
    if not game.demo and not game.bot_token:
        raise SystemExit("DEMO_MODE=false requires BOT_TOKEN in .env")
    if game.payments_enabled and (os.environ.get('RUN_BOT_POLLING','false').lower()!='true' or not os.environ.get('MINI_APP_URL','').startswith('https://')):
        raise SystemExit('Star payments require RUN_BOT_POLLING=true and HTTPS MINI_APP_URL')
    if game.payments_enabled and (not os.environ.get('TERMS_URL','').startswith('https://') or not os.environ.get('SUPPORT_CONTACT','')):
        raise SystemExit('Star payments require TERMS_URL and SUPPORT_CONTACT')
    server = ThreadingHTTPServer((os.environ.get("HOST", "0.0.0.0"), integer(os.environ.get("PORT", "3000"), 1, 65535)), handler_for(game))
    stop = threading.Event()
    if game.bot_token and os.environ.get("RUN_BOT_POLLING", "false").lower() == "true":
        threading.Thread(target=game.bot_loop, args=(stop,), daemon=True).start()
    LOG.info("OtonGifts listening on %s:%s — %s, virtual economy", *server.server_address,
             "demo" if game.demo else "Telegram authenticated")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
