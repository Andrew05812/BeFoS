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
 * device. The plans page arms an hour and then closes, so between that arming and this wake the pair can
 * move the evening, call it off or let it pass, and the sentence still sitting in the alarm's extras
 * would arrive as news. What the device is allowed to say then depends on what the plan says now, and
 * that is a rule a test can hold rather than one the phone gets to discover.
 *
 * A moved evening is held to a second rule as well: the wake that stays quiet about the hour nobody
 * stands on must put the live one back on the clock, because a silence alone would cost the person both
 * evenings at once — the old one to a correct quiet and the new one to an alarm that was never moved
 * with it. Which hour the device wakes for, under which plan id, and what happens when the pair moves
 * the evening twice are the same test's business as the notice itself.
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
    fun `an hour the other half moved is not spoken but goes back onto the clock`() {
        // The 17th became the 18th while nobody opened the plans page. The old evening arriving on this
        // phone as news would be a wrong hour the person can still act on — and the moved one deserves
        // a call of its own, because the only screen that arms an hour is not open to do it.
        val moved = plan(startsAt = "2026-10-18T19:00:00+03:00")

        assertEquals(ReminderDelivery.Rearm(moved), deliveryFor(armed(), PlanReading.Read(moved), now))
    }

    @Test
    fun `an evening moved later is armed for its own lead rather than the one that just woke`() {
        val moved = plan(startsAt = "2026-10-18T19:00:00+03:00")

        val delivery = deliveryFor(armed(), PlanReading.Read(moved), now)
        val reArmed = reminderFor((delivery as ReminderDelivery.Rearm).plan, now)!!

        assertEquals(ZonedDateTime.of(2026, 10, 18, 18, 0, 0, 0, moscow), reArmed.firesAt)
        assertEquals(moved.startsAt, reArmed.agreedHourIso)
        // The same plan id is what makes the new hour take the old one's slot on the device rather than
        // stand beside it as a second alarm for the same evening.
        assertEquals("p1", reArmed.planId)
    }

    @Test
    fun `an evening moved earlier is armed for its own lead`() {
        // The pair pulled the meeting in from two days off to this afternoon. A person who only heard
        // the old hour would have had two days to get ready for an evening two hours away.
        val moved = plan(startsAt = "2026-10-15T14:00:00+03:00")

        val delivery = deliveryFor(armed(), PlanReading.Read(moved), now)
        val reArmed = reminderFor((delivery as ReminderDelivery.Rearm).plan, now)!!

        assertEquals(ZonedDateTime.of(2026, 10, 15, 13, 0, 0, 0, moscow), reArmed.firesAt)
        assertEquals("Через час — Сегодня, 14:00", reArmed.text)
    }

    @Test
    fun `an evening moved inside the lead is armed for the hour itself`() {
        // Half an hour left. The lead slipped behind this moment, so the call moves to the hour and
        // arrives late rather than not at all.
        val moved = plan(startsAt = "2026-10-15T12:30:00+03:00")

        val delivery = deliveryFor(armed(), PlanReading.Read(moved), now)
        val reArmed = reminderFor((delivery as ReminderDelivery.Rearm).plan, now)!!

        assertEquals(ZonedDateTime.of(2026, 10, 15, 12, 30, 0, 0, moscow), reArmed.firesAt)
        assertTrue(reArmed.text, reArmed.text.startsWith("Сейчас — "))
    }

    @Test
    fun `an evening moved past this moment is armed for a lead still ahead of it`() {
        // The device wakes at 18:00 on the 17th and the pair has moved the evening to the 18th 19:00.
        // Re-arming from that wake has to leave a call in the future, or the phone would go on waking
        // itself for an hour it has already passed.
        val woke = clock(17, 18)
        val moved = plan(startsAt = "2026-10-18T19:00:00+03:00")

        val delivery = deliveryFor(armed(), PlanReading.Read(moved), woke)
        val reArmed = reminderFor((delivery as ReminderDelivery.Rearm).plan, woke)!!

        assertTrue(reArmed.firesAt.toString(), !reArmed.firesAt.toInstant().isBefore(woke.toInstant()))
    }

    @Test
    fun `a moved evening the clock walked past while this device slept is left off the clock`() {
        // Nothing to arm for a meeting nobody is going to any more, and no notice about an hour gone.
        val passed = plan(startsAt = "2026-10-15T11:00:00+03:00")

        assertEquals(ReminderDelivery.Silent, deliveryFor(armed(), PlanReading.Read(passed), now))
    }

    @Test
    fun `a plan the pair called off while this device slept is not put back on the clock`() {
        // The hour is still written on the row, so it is the state rather than the number that decides.
        val calledOff = plan(status = PlanStatuses.CANCELLED, startsAt = "2026-10-18T19:00:00+03:00")

        assertEquals(ReminderDelivery.Silent, deliveryFor(armed(), PlanReading.Read(calledOff), now))
    }

    @Test
    fun `a meeting both have marked as kept is not put back on the clock`() {
        val kept = plan(status = PlanStatuses.COMPLETED, startsAt = "2026-10-18T19:00:00+03:00")

        assertEquals(ReminderDelivery.Silent, deliveryFor(armed(), PlanReading.Read(kept), now))
    }

    @Test
    fun `an hour the server could not answer for is spoken with its doubt and never armed afresh`() {
        // An unconfirmed moment is not a thing to wake a device for. The notice goes out with its doubt
        // named, and the clock stays as the plans page left it.
        val delivery = deliveryFor(armed(), PlanReading.Unreachable, now)

        assertTrue(delivery.toString(), delivery is ReminderDelivery.Speak)
        assertEquals(
            ReminderDelivery.Speak(
                "Поход в кино",
                "Через час — строка, которую страница написала ранее$REMINDER_NOT_VERIFIED_SUFFIX",
            ),
            delivery,
        )
    }

    @Test
    fun `an hour the pair only reprinted with another offset is spoken rather than armed again`() {
        // The pair moved nothing; the server wrote the same evening in UTC. Re-arming on a change of
        // characters would give one agreed hour as many alarms as the service has formats.
        val rewritten = plan(startsAt = "2026-10-17T16:00:00+00:00")

        val delivery = deliveryFor(armed(), PlanReading.Read(rewritten), now)

        assertTrue(delivery.toString(), delivery is ReminderDelivery.Speak)
    }

    @Test
    fun `a moved evening the server writes in the partner's offset is armed for that moment`() {
        // 20:00 where the partner is, 18:00 here. The move is real, so the hour goes back on the clock
        // at the moment it names rather than at the characters it was written in.
        val moved = plan(startsAt = "2026-10-18T20:00:00+05:00")

        val delivery = deliveryFor(armed(), PlanReading.Read(moved), now)
        val reArmed = reminderFor((delivery as ReminderDelivery.Rearm).plan, now)!!

        assertEquals(ZonedDateTime.of(2026, 10, 18, 17, 0, 0, 0, moscow), reArmed.firesAt)
    }

    @Test
    fun `two wakes of one moved evening arm one hour rather than two`() {
        // A dozing device hands the same alarm over again a few minutes later. Both wakes read the same
        // moved evening, so what goes onto the clock has to be that one hour under that one plan id —
        // a lead measured from the wake itself would put a second alarm beside the first.
        val moved = plan(startsAt = "2026-10-18T19:00:00+03:00")
        val first = reminderFor(
            (deliveryFor(armed(), PlanReading.Read(moved), now) as ReminderDelivery.Rearm).plan,
            now,
        )!!
        val second = reminderFor(
            (deliveryFor(armed(), PlanReading.Read(moved), now.plusMinutes(4)) as ReminderDelivery.Rearm).plan,
            now.plusMinutes(4),
        )!!

        assertEquals(first.agreedHourIso, second.agreedHourIso)
        assertEquals(first.planId, second.planId)
        assertEquals(first.firesAt.toInstant(), second.firesAt.toInstant())
    }

    @Test
    fun `an evening moved twice is armed once per move and then spoken at the hour it stands on`() {
        // The whole life of one reminder through two moves: the page armed the 17th, the partner made it
        // the 18th, the wake re-armed that hour, the partner moved it again to the 19th, the second wake
        // re-armed again — and a wake that finds its own hour still the live one speaks instead of
        // arming, which is what keeps this from going round for ever.
        val toTheEighteenth = plan(startsAt = "2026-10-18T19:00:00+03:00")
        val firstWake = reminderFor(
            (deliveryFor(armed(), PlanReading.Read(toTheEighteenth), now) as ReminderDelivery.Rearm).plan,
            now,
        )!!
        assertEquals(ZonedDateTime.of(2026, 10, 18, 18, 0, 0, 0, moscow), firstWake.firesAt)

        // The second wake, at the lead the first one wrote down, with the plan unchanged.
        val spoken = deliveryFor(firstWake, PlanReading.Read(toTheEighteenth), firstWake.firesAt)
        assertTrue(spoken.toString(), spoken is ReminderDelivery.Speak)

        // The partner moves it once more before that hour arrives.
        val woke = firstWake.firesAt
        val toTheNineteenth = plan(startsAt = "2026-10-19T19:00:00+03:00")
        val secondWake = reminderFor(
            (deliveryFor(firstWake, PlanReading.Read(toTheNineteenth), woke) as ReminderDelivery.Rearm).plan,
            woke,
        )!!

        assertEquals(ZonedDateTime.of(2026, 10, 19, 18, 0, 0, 0, moscow), secondWake.firesAt)
        assertEquals("p1", secondWake.planId)
        assertTrue(
            deliveryFor(secondWake, PlanReading.Read(toTheNineteenth), secondWake.firesAt)
            is ReminderDelivery.Speak,
        )
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
