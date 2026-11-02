"""A page link the server issued, and the one refusal every broken link gets.

Before this module a cursor was whatever the client put in the URL: ``rank:<число>`` from the deck and
``tap:<микросекунды>:<id>`` from the tap list (`app/services/discovery_service.py`). Both were checked
for shape and bounded so a typed digit run could not reach SQL and raise there, and both were then
believed. That was harmless while the only thing behind the link was a place in the reader's own list —
and it was the reason `docs/RELEASE.md` §11 item 10 stayed open: the payload was still the client's
claim, so the day a page had to carry something the server is obliged to remember, every door would have
needed its own answer about who told it that number.

What a link carries now, sealed:

```
base64url("v1|<kid>|<door>|<reader hex>|<window>|<place>") + "." + base64url(hmac_sha256)
```

The ``door`` half is why two lists of the same shape cannot read each other's links: the deck, the
inbox, the tap list, the pass list and the pair list each accept only the name they were issued under.
The ``reader`` half is why a link is not portable between accounts at all — it is a place in somebody's
history, and carrying it to another door used to answer that other person's rows from a boundary a
stranger chose.

Every refusal is the same `BAD_CURSOR` sentence at the same status. A refusal that said which half
failed — the key, the version, the age, the account — would be a probe for the signing rule, and a
refusal that echoed the payload would put a live link into whatever the caller logs. Nothing here names
HMAC, a key id or an expiry: those are the server's own words about its own check, and they belong in
the documents, not in an API response.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.exceptions import ValidationError

BAD_CURSOR = "The link to the next page is broken."

# The version of the envelope. A link is short-lived, so a server only ever holds one version at a
# time — but the field is in the payload from the first release, because the day it is two, the
# refusal of the old shape has to be a decision rather than a coincidence of parsing.
VERSION = "v1"
_FIELDS = 6
_MAX_PLACE_LEN = 128
_MICROSECOND = timedelta(microseconds=1)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
# The same ceiling the tap list put on a typed moment: `timestamptz` ends in 294276 and Python's
# `datetime` ends in year 9999, and a payload past the smaller of the two is refused as input rather
# than reaching the arithmetic that would fail on it.
_MAX_MICROS = int((datetime.max.replace(tzinfo=UTC) - _EPOCH) / _MICROSECOND)

# The doors that hand out links. The name is in the sealed payload, so a link from one is refused at
# another without either door having to know the other's key columns.
DECK = "deck"
TAPS = "taps"
INBOX = "inbox"
PASSES = "passes"
PAIRS = "pairs"
DOORS = frozenset({DECK, TAPS, INBOX, PASSES, PAIRS})

# The two shapes a place comes in. The deck is ranked once and pages by that rank, so its frontier is
# a number (`app/models/discovery.py`); the four gesture and pair lists are walked newest-first, so
# theirs is a moment and the row's own id — the pair stage 54 proved necessary, because two rows a
# microsecond apart sit on both sides of a boundary drawn through the timestamp alone.
RANK_PREFIX = "rank"
MOMENT_PREFIX = "moment"
# The ceiling on a link's window number. The shortest life the settings allow is one minute and the
# clock of this century counts about 1.8 billion seconds, so a window over a trillion is not a window
# anybody's link came from — it is somebody typing at the URL, and it is refused there rather than
# reaching the arithmetic that would compare it with now.
_MAX_WINDOW = 10**12
# `DiscoveryQueue.rank` is a PostgreSQL `integer`, and a parsed rank is bound into `rank > $n` as that
# type. A digit run past int32 is not a place in anybody's deck but a value SQL refuses, so without the
# bound a hand-typed URL answers with a 500 and a traceback. Deck ranks stay far below it: they count
# one viewer's candidates.
MAX_RANK = 2**31 - 1


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(key: bytes, body: str) -> bytes:
    return hmac.new(key, body.encode(), hashlib.sha256).digest()


def _plain_digits(text: str, bound: int) -> int | None:
    """A digit run the payload claims, converted — or nothing, when it is not a plain run.

    The rule the deck learned in stage 17 and the tap list in stage 123: `str.isdigit()` also says yes
    to ``²``, to ``٣`` and to a full-width ``１``, and `int()` then either converts something nobody
    typed or raises on a long run. Both of those are refusals here, not a value that reaches a column.
    """
    if not text.isascii() or not text.isdigit():
        return None
    if len(text) > len(str(bound)):
        return None
    value = int(text)
    return value if value <= bound else None


def _window(moment: datetime) -> int:
    """Which expiry window a moment falls in — the only age a link is allowed to claim."""
    return int(moment.timestamp()) // settings.cursor_link_seconds


def seal(door: str, reader_id: uuid.UUID, place: str, *, issued_at: datetime | None = None) -> str:
    """The link a page hands to its reader, sealed with the key the server holds.

    ``place`` is whatever the door's own codec produced for its last row — a rank, a moment and a row
    id — and this module does not look inside it. The door that sealed a link is the only thing that can
    read its own key columns, and a shared parser is how one list's bug becomes another list's page.

    The age a link carries is a window number rather than the moment it was minted, and that is what
    keeps a link repeatable: the same page asked for twice inside one window answers the same rows and
    hands out the same next link, which is the bargain the tap list has held since stage 123
    (`test_the_same_cursor_turned_twice_answers_the_same_page`). A minted timestamp would make every
    answer's own next link differ in its last characters, and a reader who retried would be told the
    page had changed when nothing but the seal's clock had ticked.
    """
    if door not in DOORS:
        raise ValueError(f"{door!r} is not a door that hands out page links")
    if not place or len(place) > _MAX_PLACE_LEN:
        raise ValueError("a page link's place is the last row the reader was shown, and it is empty")
    kid, key = settings.cursor_signing_key
    payload = f"{VERSION}|{kid}|{door}|{reader_id.hex}|{_window(issued_at or datetime.now(UTC))}|{place}"
    body = _b64e(payload.encode())
    return f"{body}.{_b64e(_sign(key, body))}"


def open_link(
    token: str, *, door: str, reader_id: uuid.UUID, now: datetime | None = None
) -> str:
    """The place a link carries, or the one refusal.

    Checked in the order that costs least and leaks nothing: the shape of the string, then the key the
    link names, then the signature over it, then whose link it was, which door it came from and whether
    it is still young enough to mean a frontier. A caller that fails any of those gets the same answer,
    because the difference between them is exactly what somebody probing the door would want to learn.

    A window number, not an instant, is what the age is compared against: a link minted at the last
    second of a window is read in the next one, so a link lives between one and two windows, and the
    documents name that span rather than pretending the setting is exact.
    """
    refused = ValidationError(BAD_CURSOR)
    body, _, signature = token.partition(".")
    if not body or not signature:
        raise refused
    try:
        raw_signature = _b64d(signature)
        payload = _b64d(body).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise refused
    parts = payload.split("|")
    if len(parts) != _FIELDS or parts[0] != VERSION:
        raise refused
    _, kid, named_door, named_reader, window_text, place = parts
    key = settings.cursor_keys.get(kid)
    if key is None or len(raw_signature) != hashlib.sha256().digest_size:
        raise refused
    if not hmac.compare_digest(raw_signature, _sign(key, body)):
        raise refused
    if named_door != door or named_reader != reader_id.hex or not place:
        raise refused
    window = _plain_digits(window_text, _MAX_WINDOW)
    if window is None:
        raise refused
    if _window(now or datetime.now(UTC)) - window > 1:
        raise refused
    return place


def seal_rank(reader_id: uuid.UUID, rank: int) -> str:
    """The deck's link: a position in a ranking this reader's queue holds."""
    return seal(DECK, reader_id, f"{RANK_PREFIX}:{rank}")


def open_rank(reader_id: uuid.UUID, cursor: str | None) -> int:
    """The rank the reader stopped at, or -1 for the top of the deck.

    An absent link and an empty one are the same question, which is how the deck has read its own
    `decode_cursor(None)` since stage 17: two ways to ask for the first page and one way to get it.
    """
    if not cursor:
        return -1
    place = open_link(cursor, door=DECK, reader_id=reader_id)
    prefix, _, digits = place.partition(":")
    if prefix != RANK_PREFIX:
        raise ValidationError(BAD_CURSOR)
    rank = _plain_digits(digits, MAX_RANK)
    if rank is None:
        raise ValidationError(BAD_CURSOR)
    return rank


def seal_moment(door: str, reader_id: uuid.UUID, when: datetime, row_id: uuid.UUID) -> str:
    """A link for a door whose rows are ordered by a moment the row itself carries."""
    micros = (when - _EPOCH) // _MICROSECOND
    return seal(door, reader_id, f"{MOMENT_PREFIX}:{micros}:{row_id.hex}")


def open_moment(
    door: str, reader_id: uuid.UUID, cursor: str | None
) -> tuple[datetime, uuid.UUID] | None:
    """Where the reader stood in this door's list, or None for its newest row."""
    if not cursor:
        return None
    place = open_link(cursor, door=door, reader_id=reader_id)
    parts = place.split(":")
    if len(parts) != 3 or parts[0] != MOMENT_PREFIX:
        raise ValidationError(BAD_CURSOR)
    micros = _plain_digits(parts[1], _MAX_MICROS)
    if micros is None:
        raise ValidationError(BAD_CURSOR)
    try:
        row_id = uuid.UUID(hex=parts[2])
    except ValueError:
        raise ValidationError(BAD_CURSOR)
    return _EPOCH + timedelta(microseconds=micros), row_id
