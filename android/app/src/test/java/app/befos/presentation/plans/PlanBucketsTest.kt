package app.befos.presentation.plans

import app.befos.domain.model.Plan
import app.befos.domain.model.PlanDecisions
import app.befos.domain.model.PlanStatuses
import java.time.ZoneId
import java.time.ZonedDateTime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The page divides the pair's plans on what they hold rather than on the word the server printed, and
 * every sentence below is read off the fields that answer: whose hour is waiting, whose word is
 * missing, whether the clock has walked past the evening. An hour that has passed is not a meeting —
 * only the two halves can say the meeting happened — so the rules that decide a card's section and
 * its buttons are written out here where a test can hold the clock still and name each case.
 */
class PlanBucketsTest {

    private val moscow = ZoneId.of("Europe/Moscow")

    /** Midday on the 15th, so the 17th is still ahead and the 14th is behind. */
    private val now = ZonedDateTime.of(2026, 10, 15, 12, 0, 0, 0, moscow)

    private val ahead = "2026-10-17T19:00:00+03:00"
    private val behind = "2026-10-14T19:00:00+03:00"
    private val them = "them"

    private fun plan(
        id: String = "p1",
        status: String = PlanStatuses.PROPOSED,
        startsAt: String? = null,
        pendingHour: String? = null,
        pendingBy: String? = null,
        myDecision: String = PlanDecisions.PENDING,
        partnerDecision: String = PlanDecisions.PENDING,
        iAttended: Boolean = false,
        partnerAttended: Boolean = false,
        hourPassed: Boolean = false,
        needsMyAnswer: Boolean = false,
        canCancel: Boolean = true,
        partnerId: String? = them,
        place: String? = null,
        note: String? = null,
    ) = Plan(
        id = id,
        title = "Поход в кино", description = null, note = note, place = place,
        status = status, startsAt = startsAt, pendingHour = pendingHour, pendingBy = pendingBy,
        myDecision = myDecision, iAttended = iAttended,
        partnerId = partnerId, partnerName = "Анна",
        partnerDecision = partnerDecision, partnerAttended = partnerAttended,
        hourPassed = hourPassed, needsMyAnswer = needsMyAnswer, canCancel = canCancel,
    )

    @Test
    fun `an idea with no hour waits ahead and an agreed hour sits under a договорённость`() {
        assertEquals(PlanBucket.AHEAD, planBucketOf(plan()))
        assertEquals(
            PlanBucket.AGREED,
            planBucketOf(plan(status = PlanStatuses.PLANNED, startsAt = ahead)),
        )
        // Both halves said yes and nobody named the evening: nothing has been arranged yet.
        assertEquals(PlanBucket.AHEAD, planBucketOf(plan(status = PlanStatuses.ACCEPTED)))
    }

    @Test
    fun `a plan being moved is not read as an agreement the pair stands on`() {
        // `starts_at` still holds the hour they are replacing, and the section caption over a plan in
        // «Договорились» promises the hour the pair stands on.
        val moving = plan(status = PlanStatuses.RESCHEDULED, startsAt = behind, pendingHour = ahead, pendingBy = them)

        assertEquals(PlanBucket.AHEAD, planBucketOf(moving))
        assertTrue(planSections(listOf(moving)).single().plans.single().id == "p1")
    }

    @Test
    fun `a passed hour does not complete a meeting the pair has not confirmed`() {
        val spent = plan(status = PlanStatuses.PLANNED, startsAt = behind, hourPassed = true)

        assertEquals(PlanBucket.AGREED, planBucketOf(spent))
        assertEquals(
            PlanBucket.DONE,
            planBucketOf(plan(status = PlanStatuses.COMPLETED, startsAt = behind, hourPassed = true)),
        )
    }

    @Test
    fun `a refusal and a cancellation leave the pair's promises behind`() {
        assertEquals(PlanBucket.GONE, planBucketOf(plan(status = PlanStatuses.CANCELLED, startsAt = ahead)))
        assertEquals(PlanBucket.GONE, planBucketOf(plan(status = PlanStatuses.DECLINED, myDecision = PlanDecisions.DECLINED)))
    }

    @Test
    fun `sections name themselves, keep the server's order and drop the empty ones`() {
        val sections = planSections(
            listOf(
                plan(id = "done", status = PlanStatuses.COMPLETED, startsAt = behind),
                plan(id = "second", status = PlanStatuses.PLANNED, startsAt = ahead),
                plan(id = "first"),
                plan(id = "third", status = PlanStatuses.PLANNED, startsAt = "2026-10-18T19:00:00+03:00"),
            ),
        )

        assertEquals(listOf("Предстоит", "Договорились", "Состоялось"), sections.map { it.title })
        // A plan the clock has not reached keeps its place among its own section's rows: the page is
        // the pair's history, and re-sorting it here would put the layout above the record.
        assertEquals(listOf("first"), sections[0].plans.map { it.id })
        assertEquals(listOf("second", "third"), sections[1].plans.map { it.id })
        assertTrue(sections.all { it.caption.isNotBlank() })
        assertFalse(sections.any { it.bucket == PlanBucket.GONE })
    }

    @Test
    fun `each state is named by the word the pair's own answers support`() {
        assertEquals("ждёт ответа партнёра", planStatusWord(plan()))
        assertEquals("ждёт вашего ответа", planStatusWord(plan(needsMyAnswer = true)))
        assertEquals(
            "вы отклонили, идея осталась у партнёра",
            planStatusWord(plan(myDecision = PlanDecisions.DECLINED)),
        )
        assertEquals("подтверждена обоими, час не назван", planStatusWord(plan(status = PlanStatuses.ACCEPTED)))
        assertEquals(
            "договорились",
            planStatusWord(plan(status = PlanStatuses.PLANNED, startsAt = ahead)),
        )
        assertEquals(
            "час прошёл",
            planStatusWord(plan(status = PlanStatuses.PLANNED, startsAt = behind, hourPassed = true)),
        )
        assertEquals(
            "новый час ждёт вашего ответа",
            planStatusWord(plan(status = PlanStatuses.RESCHEDULED, needsMyAnswer = true)),
        )
        assertEquals("новый час ждёт ответа партнёра", planStatusWord(plan(status = PlanStatuses.RESCHEDULED)))
        assertEquals(
            "вы отклонили",
            planStatusWord(plan(status = PlanStatuses.DECLINED, myDecision = PlanDecisions.DECLINED)),
        )
        assertEquals(
            "партнёр отклонил",
            planStatusWord(plan(status = PlanStatuses.DECLINED, partnerDecision = PlanDecisions.DECLINED)),
        )
        assertEquals("отменена", planStatusWord(plan(status = PlanStatuses.CANCELLED)))
        assertEquals("встреча состоялась", planStatusWord(plan(status = PlanStatuses.COMPLETED)))
    }

    @Test
    fun `half a confirmation is named as half a confirmation`() {
        // The pair's state between «ждёт ответа» and «подтверждена обоими» belongs to one of the two,
        // and the card of the person who has already said yes must not read as though nobody had.
        assertEquals(
            "подтвердили вы, ждём ответа партнёра",
            planStatusWord(plan(myDecision = PlanDecisions.JOINED)),
        )
        assertEquals(
            "ждёт вашего ответа",
            planStatusWord(plan(partnerDecision = PlanDecisions.JOINED, needsMyAnswer = true)),
        )
        // A refusal that answers the idea outranks a yes the same person gave before it, and two
        // refusals are the pair's own answer rather than one of them.
        assertEquals(
            "вы оба отклонили",
            planStatusWord(
                plan(
                    status = PlanStatuses.DECLINED,
                    myDecision = PlanDecisions.DECLINED,
                    partnerDecision = PlanDecisions.DECLINED,
                ),
            ),
        )
        assertEquals(
            "вы отказались от договорённости",
            planStatusWord(plan(status = PlanStatuses.PLANNED, startsAt = ahead, myDecision = PlanDecisions.DECLINED)),
        )
    }

    @Test
    fun `the answer doors close on the same two states for both of them`() {
        assertTrue(canAnswerPlan(plan()))
        assertTrue(canAnswerPlan(plan(status = PlanStatuses.ACCEPTED)))
        assertTrue(canAnswerPlan(plan(status = PlanStatuses.PLANNED, startsAt = ahead)))
        assertTrue(canAnswerPlan(plan(status = PlanStatuses.RESCHEDULED, startsAt = behind)))
        // A plan the partner refused is still this person's to answer — their own word is missing.
        assertTrue(canAnswerPlan(plan(status = PlanStatuses.DECLINED, partnerDecision = PlanDecisions.DECLINED)))
        assertFalse(canAnswerPlan(plan(status = PlanStatuses.CANCELLED)))
        assertFalse(canAnswerPlan(plan(status = PlanStatuses.COMPLETED)))

        // Where the doors are shut the card says so, because an absent button reads as a screen that
        // has not noticed the pair's answer rather than as a plan that takes no more of it.
        assertNull(planAnswerWord(plan()))
        assertNull(planAnswerWord(plan(status = PlanStatuses.DECLINED, partnerDecision = PlanDecisions.DECLINED)))
        assertEquals(
            "План отменён — подтверждать его больше нечего",
            planAnswerWord(plan(status = PlanStatuses.CANCELLED)),
        )
        assertEquals(
            "Встреча состоялась — подтверждать её больше нечего",
            planAnswerWord(plan(status = PlanStatuses.COMPLETED)),
        )
    }

    @Test
    fun `a state this build has not met says so instead of borrowing a promise`() {
        val word = planStatusWord(plan(status = "archived"))

        assertEquals("состояние, которое эта версия приложения не читает", word)
    }

    @Test
    fun `the hour the pair stands on is the hour the card may promise`() {
        assertTrue(planHourIsThePairWord(plan(status = PlanStatuses.PLANNED, startsAt = ahead), now))
        assertFalse(planHourIsThePairWord(plan(status = PlanStatuses.PLANNED, startsAt = behind, hourPassed = true), now))
        assertFalse(
            planHourIsThePairWord(
                plan(status = PlanStatuses.RESCHEDULED, startsAt = behind, pendingHour = ahead), now,
            ),
        )
        // The hour that stands in the rows of a refused plan is the evening its author walked back, and
        // a check-mark over it would promise the meeting this person has just said they are not coming to.
        assertFalse(planHourIsThePairWord(plan(status = PlanStatuses.DECLINED, startsAt = ahead), now))
        assertFalse(
            planHourIsThePairWord(
                plan(status = PlanStatuses.PLANNED, startsAt = ahead, myDecision = PlanDecisions.DECLINED), now,
            ),
        )
        assertFalse(planHourIsThePairWord(plan(), now))
    }

    @Test
    fun `an hour a changed answer left behind is said in the past`() {
        val refused = planHourWord(
            plan(status = PlanStatuses.DECLINED, startsAt = ahead, myDecision = PlanDecisions.DECLINED), now,
        )
        assertTrue(refused.orEmpty(), refused!!.startsWith("Час был назван: 17"))
        // The same reading on a plan whose hour the pair has not moved, only refused.
        val walkedBack = planHourWord(
            plan(status = PlanStatuses.PLANNED, startsAt = ahead, myDecision = PlanDecisions.DECLINED), now,
        )
        assertTrue(walkedBack.orEmpty(), walkedBack!!.startsWith("Час был назван: 17"))
    }

    @Test
    fun `the hour is called after the state the pair is in, not after the row`() {
        val agreed = planHourWord(plan(status = PlanStatuses.PLANNED, startsAt = ahead), now).orEmpty()
        assertTrue(agreed, agreed.startsWith("Договорились: 17"))
        assertTrue(agreed, agreed.endsWith(", 19:00"))

        val spent = planHourWord(plan(status = PlanStatuses.PLANNED, startsAt = behind, hourPassed = true), now)
        assertTrue(spent.orEmpty(), spent!!.endsWith(" · час прошёл"))

        // The row the pair is replacing keeps its hour on screen, but not under the word that names
        // the arrangement they hold.
        val moved = planHourWord(plan(status = PlanStatuses.RESCHEDULED, startsAt = behind, pendingHour = ahead), now)
        assertTrue(moved.orEmpty(), moved!!.startsWith("Прежний час: 14"))

        val kept = planHourWord(plan(status = PlanStatuses.COMPLETED, startsAt = behind, hourPassed = true), now)
        assertTrue(kept.orEmpty(), kept!!.startsWith("Встреча была: 14"))

        assertNull(planHourWord(plan(), now))
    }

    @Test
    fun `an hour this build cannot read is shown as the server sent it`() {
        val word = planHourWord(plan(status = PlanStatuses.PLANNED, startsAt = "not-an-instant"), now)

        // Not an empty agreement and not a silent row: the pair arranged something, and the text the
        // server holds is the only reading left.
        assertEquals("Договорились: not-an-instant", word)
    }

    @Test
    fun `a meeting is marked only after its hour and only by each half once`() {
        assertTrue(canMarkAttended(plan(status = PlanStatuses.PLANNED, startsAt = behind, hourPassed = true)))
        assertFalse(canMarkAttended(plan(status = PlanStatuses.PLANNED, startsAt = ahead)))
        assertFalse(
            canMarkAttended(
                plan(status = PlanStatuses.PLANNED, startsAt = behind, hourPassed = true, iAttended = true),
            ),
        )
        // The clock alone never completes a plan, and a plan that has reached «состоялось» needs no
        // second mark.
        assertFalse(canMarkAttended(plan(hourPassed = true)))
        assertFalse(canMarkAttended(plan(status = PlanStatuses.COMPLETED, hourPassed = true)))
    }

    @Test
    fun `the hour can be moved while the plan is still being arranged`() {
        assertTrue(canOfferHour(plan()))
        assertTrue(canOfferHour(plan(status = PlanStatuses.ACCEPTED)))
        assertTrue(canOfferHour(plan(status = PlanStatuses.PLANNED, startsAt = ahead)))
        assertTrue(canOfferHour(plan(status = PlanStatuses.RESCHEDULED, startsAt = behind)))
        assertFalse(canOfferHour(plan(status = PlanStatuses.COMPLETED)))
        assertFalse(canOfferHour(plan(status = PlanStatuses.CANCELLED)))
        assertFalse(canOfferHour(plan(status = PlanStatuses.DECLINED)))
        // This person's own refusal closes their editor: the idea belongs to the other half now.
        assertFalse(canOfferHour(plan(myDecision = PlanDecisions.DECLINED)))
    }

    @Test
    fun `whose word about the meeting is in gets named`() {
        assertNull(planAttendanceWord(plan()))
        assertEquals("вы отметили встречу, партнёр ещё нет", planAttendanceWord(plan(iAttended = true)))
        assertEquals("партнёр отметил встречу, ждёт вашего слова", planAttendanceWord(plan(partnerAttended = true)))
        assertEquals(
            "встречу подтвердили вы оба",
            planAttendanceWord(plan(iAttended = true, partnerAttended = true)),
        )
    }

    @Test
    fun `the plan a chat line named is brought to the row it really sits on`() {
        val sections = planSections(
            listOf(
                plan(id = "a"),
                plan(id = "b", status = PlanStatuses.PLANNED, startsAt = ahead),
                plan(id = "c", status = PlanStatuses.COMPLETED, startsAt = behind),
            ),
        )

        // One header row, then each section's own heading before its cards.
        assertEquals(1, planFocusRow("a", sections, headerRows = 1))
        assertEquals(3, planFocusRow("b", sections, headerRows = 1))
        assertEquals(5, planFocusRow("c", sections, headerRows = 1))
        // A notice over the list shifts every card down by its own row.
        assertEquals(4, planFocusRow("b", sections, headerRows = 2))
        assertNull(planFocusRow("absent", sections, headerRows = 1))
    }

    @Test
    fun `the pair can write its own words while the arrangement is still open`() {
        assertTrue(canEditPlanWords(plan()))
        assertTrue(canEditPlanWords(plan(status = PlanStatuses.ACCEPTED)))
        assertTrue(canEditPlanWords(plan(status = PlanStatuses.PLANNED, startsAt = ahead)))
        // A plan whose hour is being replaced still has a place to name: the pair arranges the two
        // separately, and refusing the words here would hide the editor from a plan that has them.
        assertTrue(
            canEditPlanWords(
                plan(status = PlanStatuses.RESCHEDULED, startsAt = behind, pendingHour = ahead),
            ),
        )
        // A meeting that happened, was called off or was refused keeps its words as history.
        assertFalse(canEditPlanWords(plan(status = PlanStatuses.COMPLETED, startsAt = behind)))
        assertFalse(canEditPlanWords(plan(status = PlanStatuses.CANCELLED, startsAt = ahead)))
        assertFalse(canEditPlanWords(plan(status = PlanStatuses.DECLINED)))
    }

    @Test
    fun `a save sends only the word that moved`() {
        val stored = plan(
            status = PlanStatuses.PLANNED, startsAt = ahead,
            place = "Кофейня у парка", note = "Возьму зонт",
        )

        // The card prefills both fields with what the row already says, so a person who edited one of
        // them would otherwise write the other back over the pair's row.
        assertEquals(
            PlanWordsEdit(note = "Кофейня на другой стороне"),
            planWordsEdit(stored, "Кофейня у парка", "Кофейня на другой стороне"),
        )
        assertEquals(
            PlanWordsEdit(place = "Библиотека"),
            planWordsEdit(stored, "Библиотека", "Возьму зонт"),
        )
        assertEquals(
            PlanWordsEdit(place = "Библиотека", note = "Позвоню у входа"),
            planWordsEdit(stored, "Библиотека", "Позвоню у входа"),
        )
        // Left as it stood: nothing to send, and the tap costs no request.
        assertTrue(planWordsEdit(stored, "Кофейня у парка", "Возьму зонт").nothingChanged)
    }

    @Test
    fun `rubbing a field clean is said as its own erasure, not as empty text`() {
        val stored = plan(
            status = PlanStatuses.PLANNED, startsAt = ahead,
            place = "Кофейня у парка", note = "Возьму зонт",
        )

        // A place that arrives blank is a refusal, so «снять место» travels on the flag the contract
        // reserves for it while the untouched note says nothing at all.
        assertEquals(PlanWordsEdit(clearPlace = true), planWordsEdit(stored, "", "Возьму зонт"))
        assertEquals(PlanWordsEdit(clearNote = true), planWordsEdit(stored, "Кофейня у парка", ""))
        assertEquals(
            PlanWordsEdit(clearPlace = true, clearNote = true),
            planWordsEdit(stored, "   ", " \n "),
        )
        // Nothing written and nothing typed: there is no erasure to ask for.
        assertTrue(planWordsEdit(plan(), "", "").nothingChanged)
    }

    @Test
    fun `the words that leave are read off the row, so stray spaces never travel`() {
        val edit = planWordsEdit(plan(), "  Пятый этаж  ", "  Позвоню у входа\n")

        assertEquals(PlanWordsEdit(place = "Пятый этаж", note = "Позвоню у входа"), edit)
    }
}
