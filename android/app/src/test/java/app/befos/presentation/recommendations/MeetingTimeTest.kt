package app.befos.presentation.recommendations

import app.befos.presentation.common.PLAN_PAST_WORD
import java.time.LocalDate
import java.time.LocalTime
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.ZonedDateTime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The hour row a card offers is the one place this product turns a wall clock into an instant, so its
 * rules are pinned here: an hour that has already struck cannot be offered, a moment the partner named
 * in their own zone is shown on this person's calendar, and an hour the pair has walked past is called
 * by the same word the chat card calls it.
 */
class MeetingTimeTest {

    private val moscow = ZoneId.of("Europe/Moscow")

    private fun clockAt(day: Int, hour: Int, minute: Int = 0) =
        ZonedDateTime.of(
            LocalDate.of(2026, 10, day),
            LocalTime.of(hour, minute),
            moscow,
        )

    @Test
    fun `an hour that has already struck today is not offered`() {
        val now = clockAt(14, 18, 30)

        assertEquals(listOf(19, 21), meetingHours(LocalDate.of(2026, 10, 14), now))
        // Tomorrow is not under way yet, so its whole row stands.
        assertEquals(listOf(10, 12, 15, 17, 19, 21), meetingHours(LocalDate.of(2026, 10, 15), now))
    }

    @Test
    fun `a day with nothing left to offer is dropped from the row`() {
        val late = clockAt(14, 22, 15)

        // A chip that opens an empty hour row is a dead tap, and the server would refuse every hour
        // of it anyway.
        assertFalse(meetingDays(late).contains(LocalDate.of(2026, 10, 14)))
        assertEquals(LocalDate.of(2026, 10, 15), meetingDays(late).first())
        assertEquals(7, meetingDays(clockAt(14, 9)).size)
    }

    @Test
    fun `today and tomorrow are named as words and the rest as dates`() {
        val now = clockAt(14, 9)

        assertEquals("Сегодня", meetingDayLabel(LocalDate.of(2026, 10, 14), now))
        assertEquals("Завтра", meetingDayLabel(LocalDate.of(2026, 10, 15), now))
        // The weekday and the number are what a plan is remembered by; the month's own punctuation
        // belongs to the system's locale data and is not what this card is about.
        val label = meetingDayLabel(LocalDate.of(2026, 10, 16), now)
        assertTrue(label, label.startsWith("пт"))
        assertTrue(label, label.contains("16"))
    }

    @Test
    fun `an offer carries this person's own zone instead of a bare wall clock`() {
        val iso = meetingInstant(LocalDate.of(2026, 10, 17), 19, moscow)

        assertEquals("2026-10-17T19:00+03:00", iso)
        // A naive string is what the server refuses: «19:00» with no zone names a moment in one of
        // the pair's two cities at random.
        assertEquals(
            OffsetDateTime.of(2026, 10, 17, 19, 0, 0, 0, ZoneOffset.ofHours(3)),
            OffsetDateTime.parse(iso),
        )
    }

    @Test
    fun `an hour the partner named in another zone reads back on this person's calendar`() {
        // Tokyo 21:00 and Moscow 15:00 are the same instant, and the hour this person is free at is
        // the one the card has to print. Slicing the string would show 21:00 to someone who cannot
        // meet at 21:00.
        val label = formatMeetingInstant("2026-10-17T21:00+09:00", clockAt(14, 9), moscow)

        assertTrue(label, label.startsWith("17"))
        assertTrue(label, label.endsWith(", 15:00"))
    }

    @Test
    fun `an offer that lands today or tomorrow is named as such`() {
        val now = clockAt(14, 9)

        assertEquals("Сегодня, 19:00", formatMeetingInstant("2026-10-14T19:00+03:00", now, moscow))
        assertEquals("Завтра, 20:00", formatMeetingInstant("2026-10-15T20:00+03:00", now, moscow))
    }

    @Test
    fun `an instant the card cannot read is named by showing nothing`() {
        // The page can only carry what the API wrote, so an unparseable value is not a plan; the
        // section must not print a half-read hour the pair never arranged.
        assertEquals("", formatMeetingInstant("19:00", clockAt(14, 9), moscow))
    }

    @Test
    fun `an agreed hour the pair walked past is named spent in the chat's own word`() {
        // Two screens, one evening. The chat card and this chip are read by the same pair, so the
        // word for a spent hour is shared rather than said twice in two ways.
        val chip = planChipText("2026-10-14T15:00+03:00", clockAt(15, 9))

        assertTrue(chip, chip.endsWith(" · $PLAN_PAST_WORD"))
        // The hour the pair arranged is still the row's own fact and stays printed.
        assertTrue(chip, chip.contains("15:00"))
    }

    @Test
    fun `an agreed hour still ahead is named as a plan and called nothing else`() {
        assertEquals("Договорились: Завтра, 19:00", planChipText("2026-10-15T19:00+03:00", clockAt(14, 9)))
    }

    @Test
    fun `a spent plan invites a new hour by name`() {
        val spent = "2026-10-14T15:00+03:00"
        val live = "2026-10-15T19:00+03:00"

        // Nothing of the old agreement is left to keep, so the tap is not called an edit.
        assertEquals("Договориться о новом часе", offerButtonLabel(spent, spent, clockAt(15, 9)))
        assertEquals("Изменить время", offerButtonLabel(live, null, clockAt(14, 9)))
        assertEquals("Договориться о времени", offerButtonLabel(null, null, clockAt(14, 9)))
    }

    @Test
    fun `an evening the pair stands on is moved by name, not arranged for the first time`() {
        val live = "2026-10-15T19:00+03:00"

        // The arrangement stays and only its moment changes: «Договориться о времени» over a plan the
        // pair already stands on would read as though nothing had been agreed yet.
        assertEquals("Перенести встречу", offerButtonLabel(null, live, clockAt(14, 9)))
        // The same holds when this person's own offer is what the row waits on — the pair's hour is
        // still the one being replaced.
        assertEquals("Перенести встречу", offerButtonLabel(live, live, clockAt(14, 9)))
    }
}
