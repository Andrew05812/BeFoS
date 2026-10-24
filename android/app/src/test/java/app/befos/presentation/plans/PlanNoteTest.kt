package app.befos.presentation.plans

import app.befos.core.network.befosJson
import app.befos.data.model.PlanDetailDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The one word about a plan that stays with a single person, decided apart from the composable.
 *
 * `shared_plan_members.personal_note` is the plan's only field that is not shared, and the two
 * decisions the page has to get right are invisible ones: what the typed text *means* against the
 * word the server already holds, and how long a word the route will still take. Both are pure, so the
 * JVM can hold the screen to them — a composable cannot be asked whether an emptied field was a
 * decision or a slip.
 *
 * The ceiling is checked at its own edge rather than in the middle: a person who lands exactly on the
 * limit the schema holds must be able to save, and one character past it must be stopped by a
 * sentence, not by a refusal arriving over the network.
 */
class PlanNoteTest {

    @Test
    fun `a word nobody changed sends nothing`() {
        assertEquals(PlanNoteChange.NOTHING, planNoteEdit("взять билеты", "  взять билеты ").change)
        assertTrue(planNoteEdit(null, "").nothingChanged)
        assertTrue(planNoteEdit("   ", "   ").nothingChanged)
    }

    @Test
    fun `a word written for the first time travels trimmed, not as it was typed`() {
        val edit = planNoteEdit(null, "  подъезд с торца \n")

        assertEquals(PlanNoteChange.WRITE, edit.change)
        assertEquals("подъезд с торца", edit.note)
        assertFalse(edit.nothingChanged)
    }

    @Test
    fun `a word rubbed clean over a written one is an erasure`() {
        val edit = planNoteEdit("взять билеты", "   ")

        assertEquals(PlanNoteChange.CLEAR, edit.change)
        assertNull(edit.note)
    }

    @Test
    fun `an emptied field that was already empty is not an erasure`() {
        // The two cases answer the same on screen and differ on the wire: sending a clear nobody asked
        // for would erase a word that another tap had just written.
        assertEquals(PlanNoteChange.NOTHING, planNoteEdit(null, "").change)
        assertEquals(PlanNoteChange.NOTHING, planNoteEdit("", "  ").change)
    }

    @Test
    fun `the ceiling is the one the route holds, and it is named at its edge`() {
        val edge = "а".repeat(PLAN_NOTE_LIMIT)
        val past = "а".repeat(PLAN_NOTE_LIMIT + 1)

        assertNull(planNoteOverfall(edge))
        assertEquals(PLAN_NOTE_LIMIT_WORD, planNoteOverfall(past))
        // Spaces the person typed are not a word, so they do not count toward a limit nobody reads.
        assertNull(planNoteOverfall(" ".repeat(PLAN_NOTE_LIMIT + 20)))
    }

    @Test
    fun `a save is offered only while it can land`() {
        assertTrue(canSavePlanNote(null, "взять билеты"))
        assertFalse(canSavePlanNote("взять билеты", "взять билеты"))
        assertTrue(canSavePlanNote("взять билеты", ""))
        assertFalse(canSavePlanNote("взять билеты", "а".repeat(PLAN_NOTE_LIMIT + 1)))
    }

    @Test
    fun `an unread word says so instead of printing an empty line`() {
        assertEquals(PLAN_NOTE_EMPTY_WORD, planNoteWord(null))
        assertEquals(PLAN_NOTE_EMPTY_WORD, planNoteWord("   "))
        assertEquals("билеты", planNoteWord("билеты"))
    }

    @Test
    fun `the private word is read from the same answer that carries the chronology`() {
        val body = """
            {
              "plan": {"id": "p1", "title": "Поход в кино", "status": "planned"},
              "events": [],
              "my_note": "взять билеты"
            }
        """.trimIndent()

        assertEquals("взять билеты", befosJson.decodeFromString<PlanDetailDto>(body).myNote)
    }

    @Test
    fun `an answer that carries no word reads as nobody wrote one`() {
        val without = """
            {"plan": {"id": "p1", "title": "Поход в кино", "status": "planned"}, "events": []}
        """.trimIndent()
        val erased = """
            {
              "plan": {"id": "p1", "title": "Поход в кино", "status": "planned"},
              "events": [],
              "my_note": null
            }
        """.trimIndent()

        assertNull(befosJson.decodeFromString<PlanDetailDto>(without).myNote)
        assertNull(befosJson.decodeFromString<PlanDetailDto>(erased).myNote)
    }

    @Test
    fun `a server that has started answering a field this build does not know costs nothing`() {
        // The page is older than some servers it will meet. An unknown key must not lose the person
        // their own word, and a missing one must not lose them the chronology they came to read.
        val future = """
            {
              "plan": {"id": "p1", "title": "Поход в кино", "status": "planned"},
              "events": [],
              "my_note": "билеты",
              "shared_feeling": "что-то новое"
            }
        """.trimIndent()

        val dto = befosJson.decodeFromString<PlanDetailDto>(future)
        assertEquals("билеты", dto.myNote)
        assertEquals("p1", dto.plan.id)
    }
}
