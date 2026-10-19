package app.befos.presentation.plans

import app.befos.domain.model.Message
import app.befos.domain.model.MessageKinds
import app.befos.domain.model.MessagePlan
import app.befos.presentation.chat.PLAN_KIND_UNKNOWN
import app.befos.presentation.chat.PLAN_KIND_WORDS
import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * One line of the pair's record, read as the history page reads it.
 *
 * The chronology is drawn from the very lines the conversation draws, so the two screens have one
 * vocabulary rather than two: a pair that compares them must find the same word for the same move, and
 * a move this build has never met must arrive as a row that says it cannot be named rather than as a
 * hole in the record. Which value a field had *before* it moved exists only in the server's own
 * sentence, so the row prints that sentence instead of rebuilding one from the plan's current fields —
 * the four rules below are the whole of that contract, and each state a history can hold is named here
 * with the clock held still.
 */
class PlanHistoryRowTest {

    private val moscow = ZoneId.of("Europe/Moscow")
    private val tokyo = ZoneId.of("Asia/Tokyo")

    private fun line(
        kind: String = MessageKinds.PLAN_AGREED,
        body: String = "Договорились о вечере",
        own: Boolean = true,
        createdAt: String = "2026-10-15T12:00:00+03:00",
        latest: Boolean = true,
        plan: MessagePlan? = MessagePlan(
            activityId = 7, activityTitle = "Поход в кино",
            whenIso = "2026-10-17T19:00:00+03:00", planId = "p1", isLatest = latest,
        ),
    ) = Message(
        id = "l-${kind}-$own", matchId = "m1", senderId = if (own) "me" else "them",
        body = body, createdAt = createdAt, isRead = true, isOwn = own, kind = kind, plan = plan,
    )

    @Test
    fun `every kind the chat names gets the same word on the history row`() {
        // Not a copy of the map: the row reads the chat's own entries, and this check is what keeps
        // the two screens from starting to call one move two different things.
        PLAN_KIND_WORDS.forEach { (kind, words) ->
            val row = planHistoryRowUi(line(kind = kind), moscow)

            assertEquals(words.overline, row.typeWord)
            assertNull(kind, row.unknownWord)
        }
    }

    @Test
    fun `a kind this build has never met names itself as unreadable and keeps its sentence`() {
        val row = planHistoryRowUi(
            line(kind = "plan_placed_by_a_newer_server", body = "Пара назвала другое место"), moscow,
        )

        assertEquals(PLAN_KIND_UNKNOWN.overline, row.typeWord)
        assertEquals(PLAN_KIND_UNKNOWN.current, row.unknownWord)
        // The line is still evidence of something the pair did, so a row that cannot name its type
        // does not throw its content away.
        assertEquals("Пара назвала другое место", row.sentence)
    }

    @Test
    fun `a row says whose tap wrote it`() {
        assertEquals("Вы", planHistoryRowUi(line(own = true), moscow).who)
        assertEquals("Партнёр", planHistoryRowUi(line(own = false), moscow).who)
    }

    @Test
    fun `the moment of the record is read on the reader's own calendar`() {
        // The pair's hour travels inside the sentence; «when did we change it» is always asked about
        // the day the reader is standing in. 23:00 in Moscow is already the next day in Tokyo.
        val late = line(createdAt = "2026-10-15T23:00:00+03:00")

        assertTrue(late.createdAt, planHistoryRowUi(late, moscow).moment.startsWith("15"))
        assertTrue(late.createdAt, planHistoryRowUi(late, moscow).moment.endsWith("23:00"))
        assertTrue(late.createdAt, planHistoryRowUi(late, tokyo).moment.startsWith("16"))
        assertTrue(late.createdAt, planHistoryRowUi(late, tokyo).moment.endsWith("05:00"))
    }

    @Test
    fun `a stamp the row cannot read leaves no time behind`() {
        // A history that prints a time nobody can place has stopped being evidence, so the unreadable
        // stamp is left out of the row's own text rather than shown as the server's raw characters.
        assertEquals("", planHistoryRowUi(line(createdAt = "15 октября вечером"), moscow).moment)
        assertEquals("", planHistoryRowUi(line(createdAt = ""), moscow).moment)
    }

    @Test
    fun `the line the arrangement now stands on is the one marked newest`() {
        assertTrue(planHistoryRowUi(line(latest = true), moscow).latest)
        assertFalse(planHistoryRowUi(line(latest = false), moscow).latest)
        // A line the plan entity never wrote holds no answer about the arrangement at all.
        assertFalse(planHistoryRowUi(line(plan = null), moscow).latest)
    }

    @Test
    fun `the sentence is the server's, with both edges of the change in it`() {
        val moved = line(
            kind = MessageKinds.PLAN_RESCHEDULED,
            body = "Час перенесён: 17 октября, 19:00 → 18 октября, 20:00",
        )

        // The value the hour had *before* the move exists in no plan row any more — the server keeps
        // it only in this line. A screen that rebuilt the sentence from the plan's current fields
        // would show the pair their new evening and nothing of the one they gave up.
        assertEquals(moved.body, planHistoryRowUi(moved, moscow).sentence)
    }

    @Test
    fun `a cancelled and a completed move are named as themselves, not as a standing plan`() {
        // Both kinds carry the hour the pair stood on, so a history that keyed its words off the
        // moment would read the end of an arrangement as the arrangement.
        assertEquals(
            "Договорённость",
            planHistoryRowUi(line(kind = MessageKinds.PLAN_CANCELLED), moscow).typeWord,
        )
        assertEquals(
            "Договорённость",
            planHistoryRowUi(line(kind = MessageKinds.PLAN_COMPLETED), moscow).typeWord,
        )
        assertEquals("Идея", planHistoryRowUi(line(kind = MessageKinds.PLAN_PROPOSED), moscow).typeWord)
    }
}
