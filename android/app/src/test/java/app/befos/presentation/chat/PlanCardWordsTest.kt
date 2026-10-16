package app.befos.presentation.chat

import app.befos.domain.model.Message
import app.befos.domain.model.MessageKinds
import app.befos.domain.model.MessagePlan
import app.befos.presentation.common.PLAN_PAST_WORD
import java.time.ZoneId
import java.time.ZonedDateTime
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The pair's plan writes a line into the thread for every move it makes, and the moves are not the
 * same act: an idea put to the pair, an hour agreed, an hour offered for a move, a plan ended. The
 * card that shows each of them is read here from the fields the server actually answers — the idea's
 * name off the catalogue, the hour off the row, and the status off the whole conversation rather
 * than the line alone — so a proposal can never be shown as a promise the pair is keeping. What the
 * row does not carry has to stay unnamed: a place the product does not store, an hour it cannot
 * parse, an idea the catalogue has dropped, a kind this build has not met.
 *
 * The clock is named here rather than read from the machine: whether the hour the pair agreed on
 * still lies ahead is the one part of the status the row does not answer, and a test that took it
 * from the wall would change its own expected word as the suite ages.
 */
class PlanCardWordsTest {

    private val moscow = ZoneId.of("Europe/Moscow")

    /** Midday on the 15th, so the evening of the 17th is still ahead and the 14th is behind. */
    private val now = ZonedDateTime.of(2026, 10, 15, 12, 0, 0, 0, moscow)

    private fun plan(
        latest: Boolean = true,
        title: String? = "Поход в кино",
        whenIso: String? = "2026-10-17T21:00+09:00",
        activityId: Int? = if (title == null) null else 7,
        planId: String? = "p1",
    ) = MessagePlan(
        activityId = activityId,
        activityTitle = title,
        whenIso = whenIso,
        planId = planId,
        isLatest = latest,
    )

    private fun line(kind: String, plan: MessagePlan?) = Message(
        id = "ev1", matchId = "m1", senderId = "them",
        // The sentence the server keeps for readers this build cannot reach. The card is not
        // supposed to echo it: its own fields are what the pair agreed on.
        body = "Договорённость: «Квест в реальности», 2026-10-19T18:00:00+00:00 (по UTC).",
        createdAt = "2026-10-14T09:00:00+00:00", isRead = false, isOwn = false,
        kind = kind, plan = plan,
    )

    @Test
    fun `a standing agreement names the idea, the hour and both halves`() {
        val ui = planCardUi(line(MessageKinds.PLAN_AGREED, plan()), "Анна", moscow, now)

        assertEquals("Договорённость", ui.overline)
        assertEquals("Поход в кино", ui.idea)
        // The hour the partner offered in Tokyo is printed on this reader's calendar, and the day
        // goes with it: a bare «15:00» would leave the pair guessing which day they hold.
        val moment = ui.moment.orEmpty()
        assertTrue(moment, moment.startsWith("17"))
        assertTrue(moment, moment.endsWith(", 15:00"))
        assertEquals("действует", ui.status)
        assertEquals("Вы и Анна", ui.who)
        assertEquals(7, ui.activityId)
    }

    @Test
    fun `the card carries the plan its line was written about`() {
        val ui = planCardUi(line(MessageKinds.PLAN_AGREED, plan()), "Анна", moscow, now)

        // A pair can talk the same idea over more than once, so the tap opens the plan the line names
        // rather than whichever card happens to share its activity.
        assertEquals("p1", ui.planId)
    }

    @Test
    fun `a line the plan entity never wrote leads to the idea instead`() {
        // Rows written before plans had their own rows carry no id, and the card must not promise the
        // plan page it cannot open.
        val ui = planCardUi(line(MessageKinds.PLAN_AGREED, plan(planId = null)), "Анна", moscow, now)

        assertNull(ui.planId)
        assertEquals(7, ui.activityId)
    }

    @Test
    fun `the card reads the catalogue name, not the sentence behind it`() {
        // The body was written when the plan was made; the title is read off the catalogue when the
        // page is drawn. Where the two differ, the card owes the pair the name the idea answers to
        // now — and «Квест в реальности» in the body stays out of it.
        val ui = planCardUi(line(MessageKinds.PLAN_AGREED, plan()), "Анна", moscow, now)

        assertEquals("Поход в кино", ui.idea)
        assertTrue(ui.idea, !ui.idea.contains("Квест"))
    }

    @Test
    fun `an agreement a later tap took back says so instead of going silent`() {
        assertEquals("отменена позже", planCardUi(line(MessageKinds.PLAN_AGREED, plan(latest = false)), "Анна", moscow, now).status)
        assertEquals("отменена", planCardUi(line(MessageKinds.PLAN_VOIDED, plan()), "Анна", moscow, now).status)
    }

    @Test
    fun `an agreement the clock walked past calls its hour spent and keeps the rest`() {
        // Nothing retires the row on the server, because the pair never said what happened after the
        // hour — they may have met, may have missed each other, may never have told. So the card reads
        // the past off the clock while drawing, and still names the idea and the moment the pair
        // arranged: that hour is the row's own fact even behind them. The tap keeps leading to the
        // idea, which is how the pair gets from a spent hour to a new one.
        val ui = planCardUi(
            line(MessageKinds.PLAN_AGREED, plan(whenIso = "2026-10-14T21:00+09:00")),
            "Анна",
            moscow,
            now,
        )

        assertEquals(PLAN_PAST_WORD, ui.status)
        assertEquals("Поход в кино", ui.idea)
        assertTrue(ui.moment.orEmpty(), ui.moment.orEmpty().startsWith("14"))
        assertEquals(7, ui.activityId)
    }

    @Test
    fun `a promise a tap took back is not renamed by its hour passing`() {
        // Where the two readings disagree, the tap wins: it is a fact the row carries, while the spent
        // hour is an inference this screen makes while drawing.
        val spent = "2026-10-14T21:00+09:00"

        assertEquals("отменена", planCardUi(line(MessageKinds.PLAN_VOIDED, plan(whenIso = spent)), "Анна", moscow, now).status)
        assertEquals("отменена позже", planCardUi(line(MessageKinds.PLAN_AGREED, plan(latest = false, whenIso = spent)), "Анна", moscow, now).status)
    }

    @Test
    fun `an hour this build cannot read is not called past`() {
        // A card that guesses retires a live promise, which is the worse of the two mistakes it can
        // make about a moment it cannot parse.
        val ui = planCardUi(line(MessageKinds.PLAN_AGREED, plan(whenIso = "завтра вечером")), "Анна", moscow, now)

        assertEquals("действует", ui.status)
        assertNull(ui.moment)
    }

    @Test
    fun `an idea the catalogue dropped is named as dropped and leads to no card`() {
        // The plan row outlives the activity it pointed at, so the card cannot invent a title; it
        // says the idea is gone, and the tap still opens the pair's list.
        val ui = planCardUi(line(MessageKinds.PLAN_AGREED, plan(title = null, activityId = null)), "Анна", moscow, now)

        assertEquals("Идея, о которой договаривались, больше недоступна", ui.idea)
        assertNull(ui.activityId)
        // The hour the pair agreed on is still the row's own fact and still stands.
        assertTrue(ui.moment.orEmpty().startsWith("17"))
    }

    @Test
    fun `a plan with no partner name yet still says whose agreement it is`() {
        val ui = planCardUi(line(MessageKinds.PLAN_AGREED, plan()), null, moscow, now)

        assertEquals("Вы и собеседник", ui.who)
    }

    @Test
    fun `an hour the row does not carry is left out of the card`() {
        assertNull(formatPlanMoment(null, moscow))
        assertNull(formatPlanMoment("  ", moscow))
        // A value this build cannot read is not an hour the pair arranged; printing the server's own
        // text would put a moment on the card that nobody agreed to.
        assertNull(formatPlanMoment("вечером в субботу", moscow))
        assertEquals("19:00", formatPlanMoment("2026-10-17T19:00+03:00", moscow)?.substringAfter(", "))
    }

    @Test
    fun `an idea put to the pair waits for an answer instead of naming an agreement`() {
        val ui = planCardUi(line(MessageKinds.PLAN_PROPOSED, plan(whenIso = null)), "Анна", moscow, now)

        assertEquals("Идея", ui.overline)
        assertEquals("ждёт ответа", ui.status)
        assertNull(ui.moment)
        assertFalse(ui.standing)
    }

    @Test
    fun `both halves behind an idea says the hour is still missing`() {
        val ui = planCardUi(line(MessageKinds.PLAN_ACCEPTED, plan(whenIso = null)), "Анна", moscow, now)

        assertEquals("подтверждена обоими, час не назван", ui.status)
        assertFalse("сдвоенное «да» ещё не договорённость", ui.standing)
    }

    @Test
    fun `a refusal reads as a refusal rather than as a broken promise`() {
        assertEquals("отклонена", planCardUi(line(MessageKinds.PLAN_DECLINED, plan(whenIso = null)), "Анна", moscow, now).status)
    }

    @Test
    fun `an hour one half offered is not the hour the pair agreed to`() {
        // A rescheduled line carries a pending offer. The card prints it, because it is the row's own
        // fact, and keeps it out of the standing agreement: the answer the other half owes is the news.
        val ahead = planCardUi(line(MessageKinds.PLAN_RESCHEDULED, plan()), "Анна", moscow, now)

        assertEquals("Договорённость", ahead.overline)
        assertEquals("новый час ждёт ответа", ahead.status)
        assertFalse(ahead.standing)
        assertTrue(ahead.moment.orEmpty(), ahead.moment.orEmpty().startsWith("17"))
    }

    @Test
    fun `an agreement the pair edited still stands, and still ages`() {
        val moved = planCardUi(line(MessageKinds.PLAN_CHANGED, plan()), "Анна", moscow, now)
        assertEquals("действует", moved.status)
        assertTrue(moved.standing)

        val spent = planCardUi(line(MessageKinds.PLAN_CHANGED, plan(whenIso = "2026-10-14T21:00+09:00")), "Анна", moscow, now)
        assertEquals(PLAN_PAST_WORD, spent.status)
        assertFalse(spent.standing)
    }

    @Test
    fun `a plan the pair ended says how it ended`() {
        val cancelled = planCardUi(line(MessageKinds.PLAN_CANCELLED, plan()), "Анна", moscow, now)
        assertEquals("отменена", cancelled.status)
        assertFalse(cancelled.standing)

        // Both halves said the meeting happened, so the clock has nothing left to report about the
        // hour it carries: a spent moment behind a completed plan is the meeting, not a broken promise.
        val completed = planCardUi(line(MessageKinds.PLAN_COMPLETED, plan(whenIso = "2026-10-14T21:00+09:00")), "Анна", moscow, now)
        assertEquals("встреча состоялась", completed.status)
        assertFalse(completed.standing)
    }

    @Test
    fun `a line the conversation moved past never reads as its current news`() {
        val kinds = listOf(
            MessageKinds.PLAN_PROPOSED,
            MessageKinds.PLAN_ACCEPTED,
            MessageKinds.PLAN_DECLINED,
            MessageKinds.PLAN_AGREED,
            MessageKinds.PLAN_RESCHEDULED,
            MessageKinds.PLAN_CHANGED,
            MessageKinds.PLAN_CANCELLED,
            MessageKinds.PLAN_COMPLETED,
            MessageKinds.PLAN_VOIDED,
        )
        kinds.forEach { kind ->
            val newest = planCardUi(line(kind, plan()), "Анна", moscow, now)
            val older = planCardUi(line(kind, plan(latest = false)), "Анна", moscow, now)

            assertTrue(kind, older.status == "отменена позже" || older.status == "позже пара сказала другое")
            assertNotEquals(kind, newest.status, older.status)
            assertFalse(kind, older.standing)
        }
    }

    @Test
    fun `a kind this build does not know says so instead of promising an agreement`() {
        val ui = planCardUi(line("plan_meeting_scheduled", plan()), "Анна", moscow, now)

        assertEquals("План пары", ui.overline)
        assertEquals("эта версия приложения её не читает", ui.status)
        assertFalse(ui.standing)
    }
}
