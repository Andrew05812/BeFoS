package app.befos.presentation.recommendations

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
 * The hour row a card offers is the one place this product turns a wall clock into an instant, so
 * its two rules are pinned here: an hour that has already struck cannot be offered, and a moment the
 * partner named in their own zone is shown on this person's calendar.
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
}
