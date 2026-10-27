package app.befos.presentation.pair

import app.befos.domain.model.PairNextPlan
import app.befos.domain.model.PairPerson
import app.befos.presentation.recommendations.planChipText
import app.befos.presentation.universe.starterDraftFor
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * The words the pair's reading surface puts on its own facts.
 *
 * Kept out of Compose so each sentence can be read and tested without a renderer, and kept this thin on
 * purpose: a reading surface adds no numbers to what the pair already has. The two people are named in the
 * order the pair's own document lists them — the same order both halves receive, so a pair discussing
 * «мы» in a chat and reading this screen see the same «мы». An unreadable moment is dropped rather than
 * guessed, because the day a pair formed is a fact about them and the phone has no way to invent one.
 */

/** The two of them, in the pair's own order, or null when the answer named nobody. */
internal fun pairPeopleWord(people: List<PairPerson>): String? =
    people.map { it.name.trim() }.filter { it.isNotEmpty() }.takeIf { it.isNotEmpty() }
        ?.joinToString(" и ")

/**
 * The day the pair formed, on this person's calendar, or null when the text is not a moment.
 *
 * The server's instant is read on the device's zone because this is a day rather than an hour: a pair
 * formed at 23:00 in one zone is formed «yesterday» in another, and the screen that says «пара с …» is
 * naming a date the two of them share, not a timestamp to be sent back anywhere.
 */
internal fun pairSinceDay(
    since: String,
    zone: ZoneId = ZoneId.systemDefault(),
): String? {
    val day = runCatching { OffsetDateTime.parse(since).atZoneSameInstant(zone).toLocalDate() }
        .getOrNull() ?: return null
    return day.format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale("ru")))
}

/** «план / плана / планов» — the count arrives from the server, so the ending is not a matter of taste. */
internal fun plansWord(count: Int): String = when {
    count % 100 in 11..14 -> "планов"
    count % 10 == 1 -> "план"
    count % 10 in 2..4 -> "плана"
    else -> "планов"
}

/** How many arrangements the pair holds, in the words the plans screen uses for the same count. */
internal fun plansTotalWord(count: Int): String = "$count ${plansWord(count)}"

/**
 * What the pair's nearest agreed hour reads as, or null when there is none.
 *
 * The sentence is [planChipText]'s — the same one the chat's plan card and the ideas card print — because
 * the pair reads all three about one evening, and a fourth wording of «завтра в 19:00» is how a plan starts
 * to look like a different plan. An hour behind them keeps its words and says it passed; this screen edits
 * nothing, so it offers no way to move it.
 */
internal fun nextPlanWord(plan: PairNextPlan?, now: ZonedDateTime = ZonedDateTime.now()): String? =
    plan?.let { if (it.startsAt.isBlank()) null else planChipText(it.startsAt, now) }

/**
 * The honest sentence about a pair with nothing standing on an hour.
 *
 * Two cases, and reading them as one would either hide plans the pair has or invent an agreement they do
 * not. Plans exist but none has an hour yet — an idea one of them proposed and the other has not answered
 * — is not the same as the pair having nothing at all.
 */
internal fun noPlanWord(plansTotal: Int): String =
    if (plansTotal <= 0) {
        "Ни одного плана пока нет"
    } else {
        "${plansTotalWord(plansTotal)} есть, но ни один ещё не стоит на часе"
    }

/** The door into the pair's own thread: what it is called, and what the tap leaves in the composer. */
internal data class PairChatDoor(val label: String, val draft: String?)

/**
 * The chat door, named after what it actually carries.
 *
 * A starter that quotes something the two of them can talk about becomes a first-person sentence the
 * reader might really have typed, so the door says it starts a conversation and hands that sentence
 * over. A starter that sends the reader back to the questionnaire is the app's own instruction, and a
 * thread should not open holding a sentence nobody wrote — the door then only opens the thread.
 * Neither wording names a partner: this page reads the pair, and the order of `people` says which of
 * the two came first in the document, not which one is holding the phone.
 */
internal fun pairChatDoor(starter: String): PairChatDoor =
    starterDraftFor(starter)?.let { PairChatDoor("Начать разговор", it) }
        ?: PairChatDoor("Открыть переписку", null)
