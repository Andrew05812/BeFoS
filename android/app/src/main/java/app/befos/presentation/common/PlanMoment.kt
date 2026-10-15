package app.befos.presentation.common

import java.time.OffsetDateTime
import java.time.ZonedDateTime

/**
 * What both screens say about a plan the clock has walked past, in one place so the chat card and
 * the idea card cannot start calling the same hour two different things.
 */
const val PLAN_PAST_WORD = "час прошёл"

/**
 * Whether the moment a pair arranged is already behind them.
 *
 * Nothing in the base marks a plan as spent: the journal row keeps saying `plan_agreed` after its
 * hour, because retiring it on the server would report an event nobody confirmed — the pair may have
 * met, may have missed each other, may never have said. So the past is read off the clock when the
 * screen draws, and the row itself stays the fact it was. An instant this build cannot parse is not
 * treated as past: a card that guesses would retire a live promise.
 */
fun planMomentPassed(iso: String?, now: ZonedDateTime): Boolean {
    if (iso.isNullOrBlank()) return false
    val at = runCatching { OffsetDateTime.parse(iso) }.getOrNull() ?: return false
    return at.toInstant().isBefore(now.toInstant())
}
