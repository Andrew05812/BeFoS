package app.befos.presentation.chat

import app.befos.domain.model.Message
import app.befos.domain.model.MessageKinds
import app.befos.domain.model.MessagePlan
import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The agreement the pair's plan wrote into the thread is not typed by anybody, so the card that
 * shows it is read here from the fields the server actually answers: the idea's name off the
 * catalogue, the hour off the row, and the status off the whole conversation rather than the line
 * alone. What the row does not carry has to stay unnamed — a place the product does not store, an
 * hour it cannot parse, an idea the catalogue has dropped.
 */
class PlanCardWordsTest {

    private val moscow = ZoneId.of("Europe/Moscow")

    private fun plan(
        latest: Boolean = true,
        title: String? = "Поход в кино",
        whenIso: String? = "2026-10-17T21:00+09:00",
        activityId: Int? = if (title == null) null else 7,
    ) = MessagePlan(
        activityId = activityId,
        activityTitle = title,
        whenIso = whenIso,
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
        val ui = planCardUi(line(MessageKinds.PLAN_AGREED, plan()), "Анна", moscow)

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
    fun `the card reads the catalogue name, not the sentence behind it`() {
        // The body was written when the plan was made; the title is read off the catalogue when the
        // page is drawn. Where the two differ, the card owes the pair the name the idea answers to
        // now — and «Квест в реальности» in the body stays out of it.
        val ui = planCardUi(line(MessageKinds.PLAN_AGREED, plan()), "Анна", moscow)

        assertEquals("Поход в кино", ui.idea)
        assertTrue(ui.idea, !ui.idea.contains("Квест"))
    }

    @Test
    fun `an agreement a later tap took back says so instead of going silent`() {
        assertEquals("отменена позже", planCardUi(line(MessageKinds.PLAN_AGREED, plan(latest = false)), "Анна", moscow).status)
        assertEquals("отменена", planCardUi(line(MessageKinds.PLAN_VOIDED, plan()), "Анна", moscow).status)
    }

    @Test
    fun `an idea the catalogue dropped is named as dropped and leads to no card`() {
        // The plan row outlives the activity it pointed at, so the card cannot invent a title; it
        // says the idea is gone, and the tap still opens the pair's list.
        val ui = planCardUi(line(MessageKinds.PLAN_AGREED, plan(title = null, activityId = null)), "Анна", moscow)

        assertEquals("Идея, о которой договаривались, больше недоступна", ui.idea)
        assertNull(ui.activityId)
        // The hour the pair agreed on is still the row's own fact and still stands.
        assertTrue(ui.moment.orEmpty().startsWith("17"))
    }

    @Test
    fun `a plan with no partner name yet still says whose agreement it is`() {
        val ui = planCardUi(line(MessageKinds.PLAN_AGREED, plan()), null, moscow)

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
}
