package app.befos.presentation.plans

import app.befos.domain.model.Plan
import app.befos.domain.model.PlanDecisions
import app.befos.domain.model.PlanStatuses
import java.time.Duration
import java.time.ZoneId
import java.time.ZonedDateTime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * What the device is told to call, and what it is told to stay quiet about.
 *
 * A reminder arrives when the app may be nowhere near the pair's page, so the rule is decided once,
 * here, where a test can hold the clock still: which plan states owe a call, at what moment the device
 * wakes, and what sentence the wake carries. The alternative — letting the notification code work out
 * for itself which plan is a договорённость — would put the pair's promise behind a second reading of it.
 */
class PlanReminderTest {

    private val moscow = ZoneId.of("Europe/Moscow")

    private fun clock(day: Int, hour: Int, minute: Int = 0) =
        ZonedDateTime.of(2026, 10, day, hour, minute, 0, 0, moscow)

    /** Midday on the 15th: the 17th is still ahead and the 14th is behind. */
    private val now = clock(15, 12)

    private val ahead = "2026-10-17T19:00:00+03:00"

    private fun plan(
        id: String = "p1",
        title: String = "Поход в кино",
        status: String = PlanStatuses.PLANNED,
        startsAt: String? = ahead,
    ) = Plan(
        id = id,
        title = title,
        description = null,
        note = null,
        place = null,
        status = status,
        startsAt = startsAt,
        pendingHour = null,
        pendingBy = null,
        myDecision = PlanDecisions.JOINED,
        iAttended = false,
        partnerId = "them",
        partnerName = "Анна",
        partnerDecision = PlanDecisions.JOINED,
        partnerAttended = false,
        hourPassed = false,
        needsMyAnswer = false,
        canCancel = true,
    )

    @Test
    fun `an agreed hour further ahead than the lead is called an hour before it`() {
        val reminder = reminderFor(plan(), now)

        assertEquals(ZonedDateTime.of(2026, 10, 17, 18, 0, 0, 0, moscow), reminder?.firesAt)
        assertEquals("p1", reminder?.planId)
        assertEquals("Поход в кино", reminder?.title)
        // The evening is named on this calendar; the month abbreviation is left to the day label,
        // because a JVM's locale data is not what this rule is being asked about.
        assertTrue(reminder!!.text, reminder.text.startsWith("Через час — 17"))
        assertTrue(reminder.text, reminder.text.endsWith(", 19:00"))
    }

    @Test
    fun `the lead is one hour`() {
        assertEquals(Duration.ofHours(1), REMINDER_LEAD)
    }

    @Test
    fun `a plan exactly one hour ahead is called at the lead, while the hour is still ahead`() {
        val reminder = reminderFor(plan(startsAt = "2026-10-15T13:00:00+03:00"), now)

        assertEquals(ZonedDateTime.of(2026, 10, 15, 12, 0, 0, 0, moscow), reminder?.firesAt)
        assertEquals("Через час — Сегодня, 13:00", reminder?.text)
    }

    @Test
    fun `an hour already inside the lead is called at itself rather than before this moment`() {
        // The reminder goes onto the clock now. A lead that has slipped behind this moment would fire
        // immediately and say «через час» to a person standing an half-hour from the door, so the call
        // moves to the hour itself and the wording moves with it.
        val reminder = reminderFor(plan(startsAt = "2026-10-15T19:00:00+03:00"), clock(15, 18, 30))

        assertEquals(ZonedDateTime.of(2026, 10, 15, 19, 0, 0, 0, moscow), reminder?.firesAt)
        assertEquals("Сейчас — Сегодня, 19:00", reminder?.text)
    }

    @Test
    fun `the hour is named on this person's calendar, not on the one the partner sent`() {
        // 22:00 where the partner is, 20:00 here. A call printing the partner's number would put this
        // person on their way two hours early.
        val reminder = reminderFor(plan(startsAt = "2026-10-15T22:00:00+05:00"), now)

        assertEquals(ZonedDateTime.of(2026, 10, 15, 19, 0, 0, 0, moscow), reminder?.firesAt)
        assertEquals("Через час — Сегодня, 20:00", reminder?.text)
    }

    @Test
    fun `an hour the clock has walked past owes no call`() {
        assertNull(reminderFor(plan(startsAt = "2026-10-14T19:00:00+03:00"), now))
        assertNull(reminderFor(plan(startsAt = "2026-10-15T11:59:00+03:00"), now))
    }

    @Test
    fun `only a договорённость both halves stand on is worth a call`() {
        // An idea nobody has backed, and one both backed without naming an evening.
        assertNull(reminderFor(plan(status = PlanStatuses.PROPOSED, startsAt = null), now))
        assertNull(reminderFor(plan(status = PlanStatuses.ACCEPTED, startsAt = null), now))
        // A plan being moved carries the hour the pair is replacing, and the new one waits for a word.
        assertNull(reminderFor(plan(status = PlanStatuses.RESCHEDULED), now))
        assertNull(reminderFor(plan(status = PlanStatuses.CANCELLED), now))
        assertNull(reminderFor(plan(status = PlanStatuses.DECLINED), now))
        // Both said the meeting happened: there is nothing left to be on time for.
        assertNull(reminderFor(plan(status = PlanStatuses.COMPLETED), now))
        // A state this build has not met is not read as a promise.
        assertNull(reminderFor(plan(status = "archived"), now))
    }

    @Test
    fun `a row without an hour calls nobody`() {
        assertNull(reminderFor(plan(startsAt = null), now))
        assertNull(reminderFor(plan(startsAt = "   "), now))
    }

    @Test
    fun `an instant this build cannot parse yields no reminder rather than a guessed one`() {
        // The cards can show the text the server sent; an alarm cannot, because it has to be set
        // against a moment. A call at a wrong hour is worse than no call at all.
        assertNull(reminderFor(plan(startsAt = "not-an-instant"), now))
        // A naive string names no zone, and the pair is often in two cities.
        assertNull(reminderFor(plan(startsAt = "2026-10-17T19:00:00"), now))
    }
}
