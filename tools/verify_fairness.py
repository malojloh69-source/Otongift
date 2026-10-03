#!/usr/bin/env python3
"""Verify proof JSON copied from the app: python tools/verify_fairness.py proof.json."""
import hashlib
import hmac
import json
import math
import sys

proof = json.load(open(sys.argv[1], encoding='utf-8'))
seed = proof['server_seed']
assert hashlib.sha256(seed.encode()).hexdigest() == proof['commitment'], 'Commitment mismatch'
digest = hmac.new(seed.encode(), proof['message'].encode(), hashlib.sha256).hexdigest()
if 'digest' in proof:
    assert digest == proof['digest'], 'Digest mismatch'
if 'roll' in proof:
    assert int(digest, 16) % 10000 == proof['roll'], 'Roll mismatch'
    print('Valid proof. Roll:', proof['roll'], '/ 10000')
else:
    u = int(digest[:13], 16) / 2**52
    crash = min(10000, max(100, math.floor(97 / max(u, 1 / 2**52)))) / 100
    if 'crash' in proof:
        assert crash == proof['crash'], 'Crash mismatch'
    print('Valid proof. Crash:', crash, 'x')
