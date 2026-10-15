package app.befos.presentation.recommendations

import app.befos.domain.model.Activity
import app.befos.domain.model.Recommendation
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * A tap on the chat's agreement card promises the pair that the idea it names lands under their
 * eyes. The page above the cards is not fixed — a choice that failed to record adds a line, a
 * refusal that failed adds another, a list whose ideas have all been pushed away leaves a sentence
 * where the cards were — so the row is counted against the same flags the list reads. Landing on
 * the wrong card would be worse than not scrolling at all, which is why an idea this page no longer
 * holds answers null.
 */
class PlanFocusIndexTest {

    private fun rec(id: Int) = Recommendation(
        activity = Activity(id = id, slug = "s$id", title = "Идея $id", description = null, category = "leisure"),
        score = 60, position = id, reasons = emptyList(), selected = false, partnerSelected = false,
        declined = false, myMeetingTime = null, partnerMeetingTime = null, iAcceptedTime = null, agreedTime = null,
    )

    @Test
    fun `the intro line over the list is the row the first idea sits on`() {
        assertEquals(1, planFocusIndex(7, listOf(rec(7), rec(8)), emptyList(), null, null))
        assertEquals(2, planFocusIndex(8, listOf(rec(7), rec(8)), emptyList(), null, null))
    }

    @Test
    fun `a notice above the list shifts every card down by its own row`() {
        // Two independent failures, two lines, and the idea the chat named is that many rows lower.
        assertEquals(2, planFocusIndex(7, listOf(rec(7)), emptyList(), "не записано", null))
        assertEquals(2, planFocusIndex(7, listOf(rec(7)), emptyList(), null, "не отклонено"))
        assertEquals(3, planFocusIndex(7, listOf(rec(7)), emptyList(), "не записано", "не отклонено"))
    }

    @Test
    fun `an idea in the refused section is counted past the section that opens it`() {
        val ideas = listOf(rec(7), rec(8))
        val refused = listOf(rec(9), rec(10))

        // Rows: intro, card 7, card 8, «ВЫ ОТКЛОНИЛИ», card 9, card 10.
        assertEquals(4, planFocusIndex(9, ideas, refused, null, null))
        assertEquals(5, planFocusIndex(10, ideas, refused, null, null))
    }

    @Test
    fun `a page with nothing left to show still holds its sentence above the refused cards`() {
        // Every idea pushed away: the list prints «Здесь не осталось идей» where the cards were, and
        // the refusal section follows its own header.
        // Rows: intro, «Здесь не осталось идей», «ВЫ ОТКЛОНИЛИ», the refused card.
        assertEquals(3, planFocusIndex(9, emptyList(), listOf(rec(9)), null, null))
    }

    @Test
    fun `an idea the page does not carry is answered with no row at all`() {
        assertNull(planFocusIndex(11, listOf(rec(7), rec(8)), listOf(rec(9)), null, null))
    }
}
