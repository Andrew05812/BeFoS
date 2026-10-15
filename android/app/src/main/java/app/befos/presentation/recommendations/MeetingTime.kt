package app.befos.presentation.recommendations

import app.befos.presentation.common.PLAN_PAST_WORD
import app.befos.presentation.common.planMomentPassed
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * The hours a card can offer. A date is named by the hour, not by a minute: «19:00» reads as an
 * evening plan, «19:07» reads as a stopwatch, and the pair has no reason to split a minute.
 */
private val OFFER_HOURS: List<Int> = listOf(10, 12, 15, 17, 19, 21)

/** A week ahead: far enough to arrange something, close enough that the last chip is still a plan. */
private const val OFFER_DAYS = 7

/**
 * The hours still ahead of this clock. A day that is already under way cannot be met at in an hour
 * that has struck, and the server refuses a past moment, so the row hides those hours instead of
 * offering a tap that is certain to fail.
 */
fun meetingHours(date: LocalDate, now: ZonedDateTime): List<Int> {
    if (date != now.toLocalDate()) return OFFER_HOURS
    return OFFER_HOURS.filter { it > now.hour }
}

/**
 * The days a person can choose from. A day whose every offerable hour has passed is dropped rather
 * than left as a chip that opens an empty hour row: at 22:00 there is nothing to meet at today.
 */
fun meetingDays(now: ZonedDateTime): List<LocalDate> =
    (0 until OFFER_DAYS)
        .map { now.toLocalDate().plusDays(it.toLong()) }
        .filter { meetingHours(it, now).isNotEmpty() }

/** Today and tomorrow named as words, because a plan reads as «завтра в 19:00», not as a date. */
fun meetingDayLabel(date: LocalDate, now: ZonedDateTime): String = when (date) {
    now.toLocalDate() -> "Сегодня"
    now.toLocalDate().plusDays(1) -> "Завтра"
    else -> date.format(DateTimeFormatter.ofPattern("EEE d MMM", Locale("ru")))
}

/** Printed in the device's own numbering: an hour chip must not pick up a locale's digits. */
fun meetingHourLabel(hour: Int): String = String.format(Locale.ROOT, "%02d:00", hour)

/**
 * The instant the API asks for: a whole hour on this person's own calendar, printed with its UTC
 * offset. A naive string would be refused — the pair is often in two cities, and «19:00» with no
 * zone names a moment in one of them at random.
 */
fun meetingInstant(date: LocalDate, hour: Int, zone: ZoneId): String =
    LocalDateTime.of(date, LocalTime.of(hour, 0))
        .atZone(zone)
        .toOffsetDateTime()
        .toString()

/**
 * The server's instant read back on this person's calendar. The card shows the hour the way the
 * pair arranged it, so a partner in another zone does not put a shifted number on this screen.
 */
fun formatMeetingInstant(
    iso: String,
    now: ZonedDateTime = ZonedDateTime.now(),
    zone: ZoneId = ZoneId.systemDefault(),
): String {
    // The same reading the chat applies to its timestamps: the wire carries an instant, the screen
    // shows it on this person's calendar.
    val at = runCatching { OffsetDateTime.parse(iso).atZoneSameInstant(zone) }.getOrNull() ?: return ""
    val time = at.format(DateTimeFormatter.ofPattern("HH:mm"))
    val day = when (at.toLocalDate()) {
        now.toLocalDate() -> "Сегодня"
        now.toLocalDate().plusDays(1) -> "Завтра"
        else -> at.format(DateTimeFormatter.ofPattern("d MMM", Locale("ru")))
    }
    return "$day, $time"
}

/**
 * What the card says about the moment the pair agreed on.
 *
 * A plan the clock has walked past keeps its chip: the agreement happened, and the row the pair
 * reads is the fact of it. What the card adds is that the hour is behind them, in the same words the
 * chat card uses, because one pair reads both screens and cannot be told the same evening is a
 * standing plan on one and a spent one on the other.
 */
fun planChipText(plan: String, now: ZonedDateTime): String {
    // The hour is read on the calendar of the clock this function is handed, not on the machine's
    // default zone: a chip that mixed the two would name the pair's evening at a different hour on a
    // test stand, in another country, or on a person whose screen clock and device zone disagree.
    val moment = formatMeetingInstant(plan, now, now.zone)
    return if (planMomentPassed(plan, now)) "Договорились: $moment · $PLAN_PAST_WORD" else "Договорились: $moment"
}

/**
 * What the tap that opens the hour row is called.
 *
 * Once the agreed hour is behind them the pair is not editing a plan they still stand on — there is
 * nothing of it left to keep — so the row invites a new evening by name. Calling that «Изменить
 * время» would leave the person to work out which of the two the tap does.
 */
fun offerButtonLabel(mine: String?, plan: String?, now: ZonedDateTime): String = when {
    plan != null && planMomentPassed(plan, now) -> "Договориться о новом часе"
    mine != null -> "Изменить время"
    else -> "Договориться о времени"
}
