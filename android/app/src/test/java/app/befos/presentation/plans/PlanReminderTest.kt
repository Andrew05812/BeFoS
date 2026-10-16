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
 *
 * The second half of the file holds the clock still for the moment the alarm has already woken the
 * device. The plans page is the only place that re-arms an hour, so between that arming and this wake the
 * pair can move the evening, call it off or let it pass, and the sentence still sitting in the alarm's
 * extras would arrive as news. What the device is allowed to say then depends on what the plan says now,
 * and that is a rule a test can hold rather than one the phone gets to discover.
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

    /**
     * The sentence the page left in the alarm's extras.
     *
     * Deliberately worded differently from anything a fresh read would produce: a delivery test that
     * asserted on the armed text could not tell a live sentence from the one the alarm was handed, and
     * the whole point of the read is that the pair may have moved the evening since it was written.
     */
    private fun armed(
        planId: String = "p1",
        agreedHourIso: String = ahead,
    ) = PlanReminder(
        planId = planId,
        title = "Поход в кино",
        text = "Через час — строка, которую страница написала ранее",
        firesAt = clock(17, 18),
        agreedHourIso = agreedHourIso,
    )

    @Test
    fun `an hour both readings stand on is spoken in the words of the live plan`() {
        val delivery = deliveryFor(armed(), PlanReading.Read(plan()), now)

        assertEquals(
            ReminderDelivery.Speak("Поход в кино", reminderFor(plan(), now)!!.text),
            delivery,
        )
    }

    @Test
    fun `one evening the server writes with another offset is still this hour`() {
        // 19:00 at +03:00 and 16:00 UTC are the pair's one agreed evening. Comparing the characters
        // instead would leave every reminder on this phone silent the day the server changes how it
        // prints a zone, which is a thing no user did to their plan.
        val utcIso = "2026-10-17T16:00:00+00:00"

        val delivery = deliveryFor(armed(), PlanReading.Read(plan(startsAt = utcIso)), now)

        assertEquals(
            ReminderDelivery.Speak("Поход в кино", reminderFor(plan(startsAt = utcIso), now)!!.text),
            delivery,
        )
    }

    @Test
    fun `an hour the other half moved leaves the alarm silent`() {
        // The 17th became the 18th while nobody opened the plans page. The old evening arriving on this
        // phone as news would be a wrong hour the person can still act on — their plans page is the
        // one place that already holds the moved one.
        val delivery = deliveryFor(
            armed(),
            PlanReading.Read(plan(startsAt = "2026-10-18T19:00:00+03:00")),
            now,
        )

        assertEquals(ReminderDelivery.Silent, delivery)
    }

    @Test
    fun `a plan the pair called off leaves the alarm silent`() {
        assertEquals(
            ReminderDelivery.Silent,
            deliveryFor(armed(), PlanReading.Read(plan(status = PlanStatuses.CANCELLED)), now),
        )
    }

    @Test
    fun `a meeting both have marked as kept leaves the alarm silent`() {
        assertEquals(
            ReminderDelivery.Silent,
            deliveryFor(armed(), PlanReading.Read(plan(status = PlanStatuses.COMPLETED)), now),
        )
    }

    @Test
    fun `an hour the clock walked past while this device slept leaves the alarm silent`() {
        assertEquals(
            ReminderDelivery.Silent,
            deliveryFor(armed(), PlanReading.Read(plan(startsAt = "2026-10-14T19:00:00+03:00")), now),
        )
    }

    @Test
    fun `a plan this person may no longer read leaves the alarm silent`() {
        // 403 or 404: the pair dissolved or the plan went. Nothing is left to be on time for, and the
        // server's refusal is itself the answer rather than a gap to speak across.
        assertEquals(ReminderDelivery.Silent, deliveryFor(armed(), PlanReading.Refused, now))
    }

    @Test
    fun `an hour the server could not answer for is spoken with its doubt named`() {
        // No signal, no session left, a window that closed. The hour was real when it was written down,
        // so silence would be the network's failure turned into the person missing their own evening.
        assertEquals(
            ReminderDelivery.Speak(
                "Поход в кино",
                "Через час — строка, которую страница написала ранее$REMINDER_NOT_VERIFIED_SUFFIX",
            ),
            deliveryFor(armed(), PlanReading.Unreachable, now),
        )
    }

    @Test
    fun `a sentence whose own hour this build cannot place speaks its doubt rather than the live hour`() {
        // An alarm armed by an older build, still sitting on the device after an update. The live plan
        // says an hour stands, but nothing here proves the armed sentence promises that one, so the
        // fresh words cannot be spoken over it and the old ones cannot be offered as a checked hour.
        val delivery = deliveryFor(
            armed(agreedHourIso = "не-мгновение"),
            PlanReading.Read(plan()),
            now,
        )

        assertEquals(
            ReminderDelivery.Speak(
                "Поход в кино",
                "Через час — строка, которую страница написала ранее$REMINDER_NOT_VERIFIED_SUFFIX",
            ),
            delivery,
        )
    }
}
