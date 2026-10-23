from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime, timedelta, timezone
from typing import Mapping, NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.tracker import Event, tracker
from app.compatibility.engine import CompatibilityInput, CompatibilityResult, compute_compatibility
from app.core.exceptions import NotFoundError, ValidationError
from app.models import PHOTO_DISPLAY_ORDER, Photo, Profile
from app.models.base import age_years, utc_today
from app.repositories.social_repo import DiscoveryRepository, SocialRepository
from app.repositories.user_repo import UserRepository
from app.services.compatibility_service import CompatibilityService

# Candidates ranked and appended in one go. Big enough that a viewer rarely waits on a
# rebuild, small enough that one rebuild never pulls the whole selection into Python.
DECK_BATCH = 150
# Refill once the undelivered part of the deck drops below this, so the next swipe is
# always served from rows that already exist.
DECK_FLOOR = 40
# How many claims one page may spend. A normal page fills in one; the rest are for the
# rows that went stale while they waited, and a page needing more than this has more
# broken promises than a refill can be expected to repair in a single request.
CLAIM_ROUNDS = 4
# How many taps one answer of «who liked me» carries. The list is read newest-first, so the cap
# cuts the oldest taps rather than the newest ones, and the flag beside it says the account had
# more. The device list made the same bargain for the same reason (auth_service.SESSIONS_SHOWN).
LIKED_ME_SHOWN = 50
# How many dismissed people one page of the account's own pass list carries. The same bargain as the
# inbox and for the same reason: the read is newest-first, so the cap cuts the oldest answers, and
# the flag beside it admits the rest exist.
PASSED_SHOWN = 50
# How many of the account's own taps one page carries. The same bargain as the inbox and the pass
# list, for the same reason: read newest-first, so the cap cuts the oldest taps, and the flag beside
# it admits the rest exist. This is the one door of the three whose rest the reader can ask for —
# stage 123 gave it a cursor, and the inbox and the pass list are the open end it names.
LIKED_SHOWN = 50

CURSOR_PREFIX = "rank"
BAD_CURSOR = "The link to the next page is broken."
# `DiscoveryQueue.rank` is a PostgreSQL `integer`, and the parsed cursor is bound into
# `rank > $1` as that type. A digit string beyond int32 is not a place in anybody's deck
# but a value SQL refuses, so without the bound a hand-typed URL answers with a 500 and a
# traceback. Deck ranks stay far below the limit: they count one viewer's candidates.
MAX_RANK = 2**31 - 1


def encode_cursor(rank: int) -> str:
    raw = f"{CURSOR_PREFIX}:{rank}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    """Where the viewer stopped. Absent means "from the top of my deck".

    A cursor is opaque to the client and comes back tampered with only if somebody is
    poking at the API by hand, so it is refused as input rather than trusted as a rank.
    """
    if not cursor:
        return -1
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise ValidationError(BAD_CURSOR)
    prefix, _, digits = raw.partition(":")
    if prefix != CURSOR_PREFIX or not digits.isdigit():
        raise ValidationError(BAD_CURSOR)
    rank = int(digits)
    if rank > MAX_RANK:
        raise ValidationError(BAD_CURSOR)
    return rank


# A page of the account's own taps resumes from where the reader stood in its own history. The place is
# named by both halves of the order the read is built on, because `created_at` alone is not a total
# order and a boundary drawn through it cuts between rows that share a microsecond — the loss stage 54
# proved for the pair's conversation, in the one table where two gestures a microsecond apart are the
# normal case rather than the accident.
TAP_CURSOR_PREFIX = "tap"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MICROSECOND = timedelta(microseconds=1)
# `timestamptz` ends in 294276 and Python's `datetime` ends in 9999; the smaller of the two is the
# bound, and a hand-typed cursor beyond it is refused as the broken link it is rather than reaching the
# arithmetic that would fail on it. Stage 17 put the same kind of bound on the deck's rank.
MAX_TAP_MICROS = (datetime.max.replace(tzinfo=timezone.utc) - _EPOCH) // _MICROSECOND


def encode_tap_cursor(tapped_at: datetime, tap_id: uuid.UUID) -> str:
    micros = (tapped_at - _EPOCH) // _MICROSECOND
    raw = f"{TAP_CURSOR_PREFIX}:{micros}:{tap_id.hex}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_tap_cursor(cursor: str | None) -> tuple[datetime, uuid.UUID] | None:
    """Where the reader stopped in its own taps. Absent or empty means "from the newest one".

    The cursor is opaque to the client and comes back shaped only if somebody is typing at the API, so
    anything that does not decode to a moment and a row is refused as input — with the deck's sentence,
    because «the link to the next page is broken» is the same fact about a different list, and two
    wordings for one fact is how two screens start disagreeing about it.
    """
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise ValidationError(BAD_CURSOR)
    parts = raw.split(":")
    if len(parts) != 3 or parts[0] != TAP_CURSOR_PREFIX or not parts[1].isdigit():
        raise ValidationError(BAD_CURSOR)
    micros = int(parts[1])
    if micros > MAX_TAP_MICROS:
        raise ValidationError(BAD_CURSOR)
    try:
        tap_id = uuid.UUID(hex=parts[2])
    except ValueError:
        raise ValidationError(BAD_CURSOR)
    return _EPOCH + timedelta(microseconds=micros), tap_id


class _RankedCandidate(NamedTuple):
    """A candidate this request has already read and scored: the row, its inputs, its result.
    The deck ranks a batch and serves cards out of it inside one request. Handing the ranked rows
    over instead of reading them again keeps the page's two halves on the same numbers: the
    percentage a card reports is the one the queue row that ordered it stores.
    """

    profile: Profile
    candidate_input: CompatibilityInput
    result: CompatibilityResult


def _highlight(viewer_profile: Profile, profile: Profile, shared_slugs: set[str], result) -> str | None:
    """One-line, data-derived answer to 'why is this person shown to me?'."""
    names = [i.name for i in profile.interests if i.slug in shared_slugs]
    if len(names) >= 2:
        return "Общие интересы: " + ", ".join(names[:3])
    if len(names) == 1:
        # Label form, not a sentence: "нравится" would disagree with a plural
        # interest name ("Иностранные языки"), and we cannot inflect for number here.
        # No quotes either — the chips above render the same names bare, and the
        # plural branch two lines up does too.
        return f"Общий интерес: {names[0]}"
    viewer_city = (viewer_profile.city or "").strip().lower()
    if viewer_city and (profile.city or "").strip().lower() == viewer_city:
        return "Из вашего города"
    best = max(result.categories, key=lambda c: c.percent, default=None)
    if best is not None and best.percent >= 70:
        return f"Высокое совпадение: {best.label.lower()} — {best.percent}%"
    return None


class DiscoveryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.social = SocialRepository(session)
        self.discovery = DiscoveryRepository(session)
        self.compatibility = CompatibilityService(session)

    @staticmethod
    def _preferences(viewer_profile: Profile) -> dict:
        return {
            "gender_pref": viewer_profile.gender_preference or [],
            "age_min": viewer_profile.age_min,
            "age_max": viewer_profile.age_max,
            "city": viewer_profile.city_preference or None,
        }

    async def _read_candidates(
        self, viewer_input: CompatibilityInput, ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, _RankedCandidate]:
        """Every candidate in ``ids`` against the viewer, in one batch per concern.

        The rows with their interest lists, then their answer vectors: three statements for the
        whole batch, and the two paths that read candidates — ranking a deck, building a page of
        cards — now share them instead of each paying its own three for the same ids. Only ids that
        carry a profile come back, so a row the selection scan named and the ``users`` table no
        longer has is simply absent, and the caller serves the candidates that are there.
        """
        profiles = {p.user_id: p for p in await self.users.get_profiles_by_ids(ids)}
        comp_profiles = await self.compatibility.tests.get_compatibility_profiles(ids)

        candidates: dict[uuid.UUID, _RankedCandidate] = {}
        for candidate_id, profile in profiles.items():
            candidate_input = CompatibilityService.input_from(
                profile, comp_profiles.get(candidate_id)
            )
            candidates[candidate_id] = _RankedCandidate(
                profile=profile,
                candidate_input=candidate_input,
                result=compute_compatibility(
                    viewer_input, candidate_input, self.compatibility.weight_config
                ),
            )
        return candidates

    async def _refill_deck(
        self, viewer_id: uuid.UUID, viewer_input: CompatibilityInput, prefs: dict
    ) -> tuple[bool, bool, dict[uuid.UUID, _RankedCandidate]]:
        """Rank a fresh batch of never-shown candidates and put it at the end of the deck.

        Returns whether the deck grew, whether the selection scan found anybody in it at all, and
        the candidates it read to rank them.

        The second answer is what the caller needs to stop asking: a scan that came back empty
        already told it «there is nobody left», and re-reading that costs the widest query in the
        system a second time. The third is what this page's cards are then built from: a deck that
        refills and serves in one request ranks people it is about to show, and reading them again
        for the card path asked the same three questions about the same ids twice.
        """
        fresh = await self.discovery.new_candidate_ids(
            viewer_id=viewer_id, limit=DECK_BATCH, **prefs
        )
        if not fresh:
            return False, False, {}
        candidates = await self._read_candidates(viewer_input, fresh)
        # Highest compatibility first. The batch came out of SQL newest-first and sorted
        # by id, so a tie keeps that order and the deck is reproducible for the same data.
        ranked = sorted(
            candidates.items(),
            key=lambda item: (-item[1].result.overall_percent, str(item[0])),
        )
        if not ranked:
            return False, True, {}
        await self.discovery.deck_append(
            viewer_id,
            [(candidate_id, candidate.result.overall_percent) for candidate_id, candidate in ranked],
            first_rank=await self.discovery.deck_next_rank(viewer_id),
        )
        return True, True, dict(ranked)

    async def _build_cards(
        self,
        viewer_profile: Profile,
        viewer_input: CompatibilityInput,
        ids: list[uuid.UUID],
        ranked: Mapping[uuid.UUID, _RankedCandidate],
    ) -> list[dict]:
        """Cards for the claimed ids, in deck order — one query per concern, not per card.

        ``ranked`` holds the candidates this request loaded to order the deck, and a claimed id in
        it is not read a second time. One that is not in it was queued by an earlier request, so
        the batch below pays for those ids and only those. What no ranking reads is the photo, and
        that stays a read for every card served.
        """
        if not ids:
            return []
        missing = [candidate_id for candidate_id in ids if candidate_id not in ranked]
        candidates = {
            candidate_id: ranked[candidate_id] for candidate_id in ids if candidate_id in ranked
        }
        candidates.update(await self._read_candidates(viewer_input, missing))
        photos = await self.users.get_primary_photos(ids)

        cards: list[dict] = []
        for candidate_id in ids:
            candidate = candidates.get(candidate_id)
            if candidate is None:
                continue
            profile = candidate.profile
            result = candidate.result
            shared_slugs = viewer_input.interests & candidate.candidate_input.interests
            cards.append(
                {
                    "user_id": str(candidate_id),
                    "name": profile.name,
                    "age": profile.age,
                    "city": profile.city,
                    "about": profile.about,
                    "dating_goal": profile.dating_goal,
                    "photo_url": photos.get(candidate_id),
                    "interests": [i.name for i in profile.interests][:8],
                    "compatibility": result.overall_percent,
                    "shared_interests_count": len(shared_slugs),
                    "highlight": _highlight(viewer_profile, profile, shared_slugs, result),
                }
            )
        return cards

    async def feed(
        self, viewer_id: uuid.UUID, *, limit: int = 20, cursor: str | None = None
    ) -> dict:
        viewer_profile = await self.users.get_profile(viewer_id)
        if viewer_profile is None:
            raise NotFoundError("Complete your profile before discovering people.")

        after_rank = decode_cursor(cursor)
        prefs = self._preferences(viewer_profile)
        # The viewer's own row is already in hand, and it is the row the preferences above were
        # read out of. Asking for it again by id cost one more profile read plus one more
        # interest list on every page — the same repeat the card path was fixed for.
        viewer_input = await self.compatibility.input_for(viewer_profile)

        # Rank more candidates before the viewer runs out, not after: the page that
        # follows a rebuild costs the same as any other.
        refilled = False
        # One selection scan answers three questions in this method — the pre-emptive refill, the
        # refill a short page might still want, and `has_unqueued_candidate` at the bottom all
        # bind the same preferences against the same rule — so its empty answer is kept rather
        # than re-asked. The scan is the widest query the product makes (docs/SCALE_PLAN.md,
        # §«Что останавливается первым»), and the page that runs out of cards was paying it three
        # times per request.
        nobody_left = False
        # The candidates this request has already read, whether it read them to rank a batch or to
        # build a card. A deck that refills and serves in the same request ranks people it is about
        # to show, and the card path used to load their rows, interests and vectors a second time.
        ranked: dict[uuid.UUID, _RankedCandidate] = {}
        if await self.discovery.deck_ready_count(viewer_id, cap=DECK_FLOOR) < DECK_FLOOR:
            refilled, found, batch = await self._refill_deck(viewer_id, viewer_input, prefs)
            ranked.update(batch)
            nobody_left = not found

        # Fill the page from the deck. A claim can come back short: a queued row is a
        # promise about a person who may have hidden or been blocked since it was written,
        # and the rows that no longer hold are dropped rather than served. The loop is
        # bounded, because a page made entirely of broken promises is a signal to stop
        # paging now, not a puzzle to solve forever.
        ids: list[uuid.UUID] = []
        last_rank = after_rank
        for _ in range(CLAIM_ROUNDS):
            if len(ids) >= limit:
                break
            rows = await self.discovery.deck_claim(
                viewer_id, after_rank=last_rank, limit=limit - len(ids)
            )
            if not rows:
                # Either the deck held only stale rows or the viewer is at its end. A
                # refill tells which; asking twice when the selection is empty would only
                # read the same answer twice, so one attempt per request is enough.
                if refilled or nobody_left:
                    break
                refilled, found, batch = await self._refill_deck(viewer_id, viewer_input, prefs)
                ranked.update(batch)
                nobody_left = not found
                if not refilled:
                    break
                continue
            last_rank = rows[-1][1]
            ids.extend(await self.discovery.deck_fresh_ids(viewer_id, [row[0] for row in rows]))

        cards = await self._build_cards(viewer_profile, viewer_input, ids, ranked)
        # The cards delivered are the cards consumed: a page that came up short still moved
        # the cursor to the last row it read, so nothing behind it is skipped and nothing
        # before it returns.
        advanced = last_rank != after_rank
        has_more = await self.discovery.deck_has_more(viewer_id, beyond_rank=last_rank)
        if not has_more and not nobody_left:
            has_more = await self.discovery.has_unqueued_candidate(viewer_id=viewer_id, **prefs)
        # The page is only delivered once: the rows it claimed are seen, and the ranking
        # that produced it is stored. Both have to survive this request.
        await self.session.commit()
        tracker.track(Event.DISCOVERY_FEED, str(viewer_id), cards=len(cards))
        return {
            "items": cards,
            "next_cursor": encode_cursor(last_rank) if advanced else None,
            "has_more": has_more,
        }


    async def liked_me(self, viewer_id: uuid.UUID) -> dict:
        """Who tapped this account, with the number their own card carried at that moment.

        Nothing here is recomputed. The deck spends a compatibility engine per card because it has
        to rank candidates nobody has scored yet; a row of ``likes`` already carries the percent the
        tapper was shown when they tapped (stage 26 wrote it into the gesture), and re-deriving it
        now would answer the reader's question with a number that was never anybody's reason.

        A score that is absent stays absent. The column is nullable, and the schema has never been
        told otherwise; answering `0` would dress an unread value up as a measured one, which is
        the defect 72-1 named for the compatibility bars.
        """
        rows = await self.discovery.liked_me(viewer_id, LIKED_ME_SHOWN + 1)
        shown = rows[:LIKED_ME_SHOWN]
        ids = [row[0] for row in shown]
        # Three batch reads for the whole page, none of them inside the loop: the same card
        # projection the match list pays for (name, birth date, city) and the one photo that leads.
        profiles = {p.user_id: p for p in await self.users.get_profile_cards(ids)}
        photos = await self.users.get_primary_photos(ids)
        today = utc_today()
        likes: list[dict] = []
        for tapper_id, score, tapped_at in shown:
            profile = profiles.get(tapper_id)
            if profile is None:
                continue
            likes.append(
                {
                    "user_id": str(tapper_id),
                    "name": profile.name,
                    "age": age_years(profile.birth_date, today),
                    "city": profile.city,
                    "photo_url": photos.get(tapper_id),
                    "compatibility": None if score is None else int(round(score * 100)),
                    "liked_at": tapped_at,
                }
            )
        return {"likes": likes, "has_more": len(rows) > LIKED_ME_SHOWN}

    async def liked(
        self, viewer_id: uuid.UUID, *, cursor: str | None = None, limit: int = LIKED_SHOWN
    ) -> dict:
        """Whom this account tapped, newest tap first, one page of them.

        The read is the mirror of the inbox and shares its projection, not its address. A card here
        is built from the same batch reads — the person's profile and leading photo — and carries the
        same number, but it is the number *this* account was shown when it made the gesture, read off
        its own ``likes`` row rather than recomputed. The pair and block exclusions come from the same
        repository rule, so a tap that a stranger answered back has already left for the match list and
        is not held up here a second time.

        ``cursor`` is the reader's own place in that list and ``limit`` how many rows a page may carry,
        both of them new here in stage 123. Before them the door answered fifty and said no more existed
        than it had already named, which was true of the page and false of the account: the stand holds
        87 / 893 / 4 493 of its own taps at the three scales its table publishes (`s122_walk.json`), so
        the cap cut three quarters of the smallest list and all but one percent of the largest, and left
        the reader no way to ask for the rest.
        """
        cards, rows, next_cursor = await self._liked_page(viewer_id, cursor=cursor, limit=limit)
        return {"likes": cards, "has_more": len(rows) > limit, "next_cursor": next_cursor}

    async def _liked_page(
        self, viewer_id: uuid.UUID, *, cursor: str | None = None, limit: int = LIKED_SHOWN
    ) -> tuple[list[dict], list, str | None]:
        before = decode_tap_cursor(cursor)
        rows = await self.discovery.liked(viewer_id, limit + 1, before=before)
        shown = rows[:limit]
        ids = [row[0] for row in shown]
        profiles = {p.user_id: p for p in await self.users.get_profile_cards(ids)}
        photos = await self.users.get_primary_photos(ids)
        today = utc_today()
        cards: list[dict] = []
        for tapped_id, score, tapped_at, _tap_id in shown:
            profile = profiles.get(tapped_id)
            if profile is None:
                continue
            cards.append(
                {
                    "user_id": str(tapped_id),
                    "name": profile.name,
                    "age": age_years(profile.birth_date, today),
                    "city": profile.city,
                    "photo_url": photos.get(tapped_id),
                    "compatibility": None if score is None else int(round(score * 100)),
                    "liked_at": tapped_at,
                }
            )
        # The next link is drawn from the last row this page named, not from the row that only proved
        # more exist: the reader who follows it starts one step past what they have already been shown,
        # and the extra row stays where it is for the page that will read it.
        next_cursor = None
        if len(rows) > limit and shown:
            _tapped_id, _score, tapped_at, tap_id = shown[-1]
            next_cursor = encode_tap_cursor(tapped_at, tap_id)
        return cards, rows, next_cursor

    async def undo_like(self, viewer_id: uuid.UUID, target_id: uuid.UUID) -> dict:
        """Take one's own tap back, and answer with the list that is left.

        This sits in the discovery service beside the list it returns, but the row it clears is the
        account's own outgoing ``likes`` row, so unlike ``unpass`` it touches no queue: a like never
        wrote a deck-memory row (stage 26 wrote only the ``likes`` row and deleted a pass), so the
        anti-join that hid the person lifts on its own the moment the row goes, and they can come back
        through the same door that hid them.

        Only the requester's own direction is removed — ``delete_like`` — because a tap says nothing
        about the tap the other person may have made. And the pair is left standing: two people who
        matched built a relationship that lives in the match list, and un-pairing is stage 105's door,
        with its own cascade over the chat and the plans. Silently dissolving a conversation from a
        "take my tap back" button would be a heavier action than the button promises.

        The pair lock is the same one a like, a pass and a block take, so a retry racing the first
        DELETE cannot report two withdrawals: whichever request holds the row removes it, and the other
        answers the 404 a stranger's pair gets. Self answers 422 instead, the way blocking and passing
        yourself do — a row that could never exist is not a missing one, and 404 would send the caller
        looking for an answer they never gave. What comes back is the page, not a boolean: the screen
        that asked paints the list the server actually holds, the bargain ``unpass`` and ``unblock``
        struck.
        """
        if viewer_id == target_id:
            raise ValidationError("You cannot act on your own profile.")
        await self.social.lock_pair(viewer_id, target_id)
        if not await self.social.delete_like(viewer_id, target_id):
            raise NotFoundError("You have not liked this user.")
        await self.session.commit()
        cards, rows, next_cursor = await self._liked_page(viewer_id)
        return {
            "likes": cards,
            "has_more": len(rows) > LIKED_SHOWN,
            "next_cursor": next_cursor,
        }

    async def passed(self, viewer_id: uuid.UUID) -> dict:
        """Whom this account dismissed, newest answer first, at most ``PASSED_SHOWN`` of them.

        The read is the mirror of the inbox and shares its projection, not its rule: the rows are the
        reader's own gestures, so they are addressed by who wrote them, and each card is built from
        the batch reads the inbox already pays for.
        """
        cards, rows = await self._passed_page(viewer_id)
        return {"passed": cards, "has_more": len(rows) > PASSED_SHOWN}

    async def _passed_page(self, viewer_id: uuid.UUID) -> tuple[list[dict], list]:
        rows = await self.discovery.passed(viewer_id, PASSED_SHOWN + 1)
        shown = rows[:PASSED_SHOWN]
        ids = [row[0] for row in shown]
        profiles = {p.user_id: p for p in await self.users.get_profile_cards(ids)}
        photos = await self.users.get_primary_photos(ids)
        today = utc_today()
        cards: list[dict] = []
        for passed_id, passed_at in shown:
            profile = profiles.get(passed_id)
            if profile is None:
                continue
            cards.append(
                {
                    "user_id": str(passed_id),
                    "name": profile.name,
                    "age": age_years(profile.birth_date, today),
                    "city": profile.city,
                    "photo_url": photos.get(passed_id),
                    "passed_at": passed_at,
                }
            )
        return cards, rows

    async def unpass(self, viewer_id: uuid.UUID, target_id: uuid.UUID) -> dict:
        """Take one's own pass back, and answer with the list that is left.

        Sitting with the deck rather than with ``MatchService.pass_user`` is the point: the gesture is
        two records, and only the one that owns the queue can clear it. ``_reject_unavailable`` in the
        like path is what makes a pass unreachable, together with ``new_candidate_ids`` refusing any
        candidate the deck has already held — deleting the ``passes`` row alone would leave that
        second lock in place and put the person on no list at all.

        The pair lock is the same one a like, a block and a purge take, so a retry racing the first
        DELETE cannot produce two releases: whichever request holds the row when its turn comes is
        the one that removes it, and the other answers the same 404 as a stranger would. Self answers
        422 instead, the way blocking yourself does — a row that could never exist is not a missing
        one, and 404 would send the caller looking for an answer they never gave. The sentence is the
        one ``MatchService._reject_unavailable`` already gives for a pass aimed at yourself, because
        it is the same input error seen from the other side; a second wording for one fact is how two
        screens start disagreeing about it.

        What comes back is the page, not a boolean: the screen that asked paints the list the server
        actually holds, the same bargain ``SafetyService.unblock`` struck.
        """
        if viewer_id == target_id:
            raise ValidationError("You cannot act on your own profile.")
        await self.social.lock_pair(viewer_id, target_id)
        if not await self.social.delete_pass(viewer_id, target_id):
            # A person this account never passed and a person nobody holds answer alike, so the route
            # cannot be used to ask whether some other pair has an answer written.
            raise NotFoundError("You have not passed this user.")
        await self.discovery.deck_release(viewer_id, target_id)
        await self.session.commit()
        cards, rows = await self._passed_page(viewer_id)
        return {"passed": cards, "has_more": len(rows) > PASSED_SHOWN}

    async def get_public_profile(
        self, viewer_id: uuid.UUID, target_id: uuid.UUID, *, for_match_member: bool = False
    ) -> dict:
        # Set only by the read that already brings the viewer's own row together with the peer's.
        viewer_profile: Profile | None = None
        if viewer_id == target_id:
            # Looking at your own card is not a visibility question: a hidden or unfinished
            # profile still has to open for the person it belongs to.
            profile = await self.users.get_profile_with_user(target_id)
        elif for_match_member:
            # The caller is not browsing the deck: a `matches` row already connects the two, and
            # the route proved membership before reaching here. Filtered by the deck's rule, this
            # path made «Скрыть из подбора» erase a pair from the screen that still listed it,
            # still carried its unread badge and still let both sides write in.
            pair = await self.users.get_match_pair_profiles(viewer_id, target_id)
            profile = pair.get(target_id)
            viewer_profile = pair.get(viewer_id)
        else:
            # The deck's own rule, asked about one id, in the same statement that brings the
            # viewer's row. `POST /users/{id}/like` already answers through this rule, so a profile
            # that is hidden, deactivated or never onboarded has to give the same "not found" here —
            # otherwise hiding is only a change of screen, and a registration that never finished the
            # questions still publishes a card carrying the local part of somebody's email as its
            # name. Asking the rule about the target alone used to leave the viewer's row to be read
            # again below, with its own interest list and its own answer vector.
            pair = await self.users.get_deck_pair_profiles(viewer_id, target_id)
            profile = pair.get(target_id)
            viewer_profile = pair.get(viewer_id)
        if profile is None:
            raise NotFoundError("User not found.")
        if await self.social.is_blocked_either(viewer_id, target_id):
            raise NotFoundError("User not found.")
        tracker.track(Event.PROFILE_VIEWED, str(viewer_id), target=str(target_id))

        if viewer_id == target_id:
            target_input = await self.compatibility.input_for(profile)
            viewer_input = target_input
        elif viewer_profile is None:
            # The read brought the card but not the viewer's row: that account has never filled a
            # profile in, and `build_input` answers it with the same "Profile not found." this path
            # gave before the two rows came in one statement.
            viewer_input = await self.compatibility.build_input(viewer_id)
            # `profile` was loaded above through the deck's own rule and carries its interests;
            # asking for the same row again by id is what made this path read a person twice.
            target_input = await self.compatibility.input_for(profile)
        else:
            # Two people, two rows already in hand, so both answer vectors come from the one batch
            # read the pair's compatibility screen was brought to in stage 25 and the pair's page in
            # stage 30 — one statement over `user_id in (…)`, not one per person.
            inputs = await self.compatibility.inputs_from([viewer_profile, profile])
            viewer_input, target_input = inputs[viewer_id], inputs[target_id]
        result = self.compatibility.score_inputs(viewer_input, target_input)
        photos_stmt = select(Photo).where(Photo.user_id == target_id).order_by(*PHOTO_DISPLAY_ORDER)
        photos = list((await self.session.execute(photos_stmt)).scalars().all())
        shared = sorted(viewer_input.interests & target_input.interests)
        name_by_slug = {i.slug: i.name for i in profile.interests}
        shared = [name_by_slug.get(s, s) for s in shared]

        return {
            "user_id": str(target_id),
            "name": profile.name,
            "age": profile.age,
            "city": profile.city,
            "about": profile.about,
            "dating_goal": profile.dating_goal,
            "gender": profile.gender,
            "interests": [i.name for i in profile.interests],
            "photos": [p.url for p in photos],
            "compatibility": result.overall_percent,
            "categories": [
                {
                    "category": c.key,
                    "label": c.label,
                    "score": c.percent,
                    "weight": c.weight,
                    # The card draws these with the same bars the pair page uses, so a band that
                    # holds the engine's neutral half has to say so here too — leaving it out
                    # would let the client default answer "measured" for a subject nobody spoke on.
                    "has_data": c.has_data,
                }
                for c in result.categories
            ],
            "shared_interests": shared,
        }
