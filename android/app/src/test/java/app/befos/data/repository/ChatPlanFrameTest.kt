package app.befos.data.repository

import app.befos.domain.model.MessagePlan
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * The plan a pair agreed on reaches this client twice: once inside a page of history and once as a
 * frame pushed while the socket is open. Both are read off the same fields, and a frame from a
 * server that has no journal — or from a newer one that adds a key this build ignores — still has
 * to parse rather than drop the line the pair is waiting for.
 */
class ChatPlanFrameTest {

    private fun obj(text: String) = Json.parseToJsonElement(text) as JsonObject

    @Test
    fun `a pushed plan frame is read field by field`() {
        val plan = planFromFrame(
            obj(
                """
                {"activity_id": 7, "activity_title": "Поход в кино", "plan_id": "0e1f",
                 "when": "2026-10-17T19:00+03:00", "is_latest": true}
                """.trimIndent(),
            ),
        )

        assertEquals(MessagePlan(7, "Поход в кино", "2026-10-17T19:00+03:00", "0e1f", true), plan)
    }

    @Test
    fun `a frame from a server that writes no plan id still parses`() {
        // The key arrived with the plan entity; a frame without it is a line of the pair's thread,
        // not a broken one, and the tap falls back to the pair's ideas.
        val plan = planFromFrame(
            obj("""{"activity_id": 7, "when": "2026-10-17T19:00+03:00", "is_latest": true}"""),
        )

        assertNull(plan.planId)
        assertEquals(7, plan.activityId)
    }

    @Test
    fun `a frame whose idea the server lost carries nothing the client cannot read`() {
        // `plan_activity_id` is cleared when the catalogue row goes away, so the id arrives as null
        // and the hour as a string; a missing key is read as absent, never as an empty title or a
        // zero-th idea, which would send the tap to a card that does not exist.
        val plan = planFromFrame(obj("""{"activity_id": null, "activity_title": null}"""))

        assertNull(plan.activityId)
        assertNull(plan.activityTitle)
        assertNull(plan.whenIso)
        assertFalse(plan.isLatest)
    }

    @Test
    fun `a plan id that is not a number keeps the tap without a target`() {
        val plan = planFromFrame(obj("""{"activity_id": "seven", "is_latest": true}"""))

        assertNull(plan.activityId)
        assertEquals(true, plan.isLatest)
    }
}
