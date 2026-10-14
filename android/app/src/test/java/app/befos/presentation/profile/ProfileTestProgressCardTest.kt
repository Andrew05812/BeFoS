package app.befos.presentation.profile

import app.befos.core.designsystem.answersWord
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A test left halfway used to be reported here as «Тест не пройден» with a «Пройти тест» button,
 * which is the copy of an untouched questionnaire. Since the test screen opens on the first
 * unmarked question, that button was true — it did continue — but the card hid the fact, so a
 * person with eight answers on the server had no way to tell continuing from starting over, and
 * «Пройти тест» over «Пройти заново» reads like the earlier answers are gone.
 *
 * These checks pin the four states the card distinguishes and the counts it quotes: the numbers
 * come from the server, so the card is only allowed to repeat them.
 */
class ProfileTestProgressCardTest {

    private val total = 21

    @Test
    fun `a questionnaire nobody has answered is offered as a new one`() {
        val lines = testProgressCopy(answered = 0, total = total, completed = false, failed = false)

        assertEquals("Тест не пройден", lines.title)
        assertEquals("Пройти тест", lines.button)
        assertFalse("an untouched test cannot have answers to continue", lines.body.contains("из $total"))
    }

    @Test
    fun `a partly answered test is offered as a continuation and names its counts`() {
        val lines = testProgressCopy(answered = 8, total = total, completed = false, failed = false)

        assertEquals("Тест начат", lines.title)
        assertEquals("Продолжить тест", lines.button)
        assertTrue(
            "the card has to quote the answers the server holds: ${lines.body}",
            lines.body.contains("8 ${answersWord(8)} из $total"),
        )
    }

    @Test
    fun `no part-answered count is reported as untouched`() {
        for (answered in 1 until total) {
            val lines = testProgressCopy(answered = answered, total = total, completed = false, failed = false)
            assertEquals("Продолжить тест", lines.button)
            assertEquals("Тест начат", lines.title)
            assertTrue("$answered of $total quoted wrongly: ${lines.body}", lines.body.contains("$answered"))
            assertTrue("$answered of $total lost its total: ${lines.body}", lines.body.contains("из $total"))
        }
    }

    @Test
    fun `the word for the count follows the count the server sent`() {
        // The counts are server-side, so the ending cannot be picked by eye: «1 ответ» and
        // «21 ответ» sit in the same card, and 11 through 14 take the plural genitive.
        assertEquals("ответ", answersWord(1))
        assertEquals("ответа", answersWord(2))
        assertEquals("ответов", answersWord(5))
        assertEquals("ответов", answersWord(11))
        assertEquals("ответов", answersWord(14))
        assertEquals("ответ", answersWord(21))
        assertEquals("ответов", answersWord(111))
    }

    @Test
    fun `a finished test is not offered as a continuation`() {
        val lines = testProgressCopy(answered = total, total = total, completed = true, failed = false)

        assertEquals("Тест пройден", lines.title)
        assertEquals("Пройти заново", lines.button)
        assertFalse("a finished test has nothing left to continue", lines.button.contains("Продолжить"))
    }

    @Test
    fun `a progress read that did not land quotes no numbers`() {
        // The counts on screen would be the last known ones, and the screen cannot tell whether
        // the server still agrees — so it says the read failed instead of repeating a number.
        val lines = testProgressCopy(answered = 8, total = total, completed = false, failed = true)

        assertEquals("Прогресс теста не загрузился", lines.title)
        assertFalse(lines.body.any { it.isDigit() })
        assertFalse(lines.button.contains("Продолжить"))
    }

    @Test
    fun `every state fills all three lines`() {
        val states = listOf(0 to false, 8 to false, total to true)
        for ((answered, completed) in states) {
            for (failed in listOf(false, true)) {
                val lines = testProgressCopy(answered, total, completed, failed)
                for (line in listOf(lines.title, lines.body, lines.button)) {
                    assertTrue("a state left a line empty: $lines", line.isNotBlank())
                }
            }
        }
    }
}
