package app.befos.presentation.test

import app.befos.domain.model.Option
import app.befos.domain.model.Question
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Where the questionnaire opens when a compatibility band sends the person to one section, and what
 * the screen says about that position.
 *
 * A test left halfway has to be entered where its work is left, not at question one — otherwise the
 * person re-taps their own earlier answers to reach the card they had not answered, and a re-tap
 * overwrites the answer they gave before. The line under the counter exists for the same reason: a
 * screen that opens on card five of twenty-one has to explain why, or the person reads it as a place
 * they lost.
 */
class SectionOpeningTest {

    private fun card(id: Int, category: String, marked: Boolean) = Question(
        id = id,
        category = category,
        trait = "t$id",
        text = "Вопрос $id",
        options = listOf(Option(id * 10 + 1, "да"), Option(id * 10 + 2, "нет")),
        selectedOptionId = if (marked) id * 10 + 1 else null,
    )

    /** Three «values» cards and three «leisure» cards, the order the catalogue hands them over. */
    private fun cards() = listOf(
        card(1, "values", marked = true),
        card(2, "values", marked = true),
        card(3, "values", marked = false),
        card(4, "leisure", marked = true),
        card(5, "leisure", marked = false),
        card(6, "leisure", marked = false),
    )

    @Test
    fun `a test opened on its own resumes at the first unmarked card`() {
        assertEquals(2, startIndex(cards(), null))
        assertEquals(2, startIndex(cards(), ""))
    }

    @Test
    fun `a section opening stays inside the section it was sent to`() {
        // Card 3 is the first unmarked card of the whole test, and the person was sent to leisure:
        // landing there would answer a section nobody asked about.
        assertEquals(4, startIndex(cards(), "leisure"))
    }

    @Test
    fun `a finished section opens on its own first card`() {
        val all = cards().map { it.copy(selectedOptionId = it.options.first().id) }
        // Nothing left to continue: the cards of the section are shown from its beginning, and the
        // line under the counter says so instead of promising an empty card.
        assertEquals(0, startIndex(all, "values"))
        assertEquals(3, startIndex(all, "leisure"))
    }

    @Test
    fun `a section the catalogue does not ask about does not dead-end the screen`() {
        // A band the questionnaire does not measure arrives as an empty group of cards. Falling back
        // to the whole-test rule keeps the screen usable; an index of -1 would show no question.
        assertEquals(2, startIndex(cards(), "goals"))
    }

    @Test
    fun `an empty catalogue opens at the first position`() {
        assertEquals(0, startIndex(emptyList(), "values"))
        assertEquals(0, startIndex(emptyList(), null))
    }

    @Test
    fun `the opening line quotes the counts it was handed`() {
        val started = sectionOpeningWord("Ценности", 2, 5)
        assertTrue(started, started.contains("2 ответа из 5"))
        assertTrue(started, started.contains("Ценности"))

        val untouched = sectionOpeningWord("Ценности", 0, 5)
        assertTrue(untouched, untouched.contains("5 ответов"))
        // Nobody has answered this section, so the line cannot blame a partner for it.
        assertFalse(untouched, untouched.contains("партн"))

        val closed = sectionOpeningWord("Ценности", 5, 5)
        assertTrue(closed, closed.contains("5 из 5"))
        // Every card of the section holds an answer: «continue» would point at a card that is not there.
        assertFalse(closed, closed.contains("Продолжаем"))
    }

    @Test
    fun `the opening line states no measurement`() {
        listOf(0 to 5, 2 to 5, 5 to 5, 3 to 0).forEach { (answered, total) ->
            val line = sectionOpeningWord("Личность", answered, total)
            assertFalse(line, line.contains("%"))
            assertTrue(line, line.contains("Личность"))
        }
    }
}
