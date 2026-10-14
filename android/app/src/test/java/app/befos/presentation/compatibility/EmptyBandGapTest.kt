package app.befos.presentation.compatibility

import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The line an empty band of the compatibility screen prints, and the action it offers.
 *
 * «нет данных» under a bar answers the question «was this measured» and leaves the next one open: a
 * person who wants that band filled has to find out whether the questionnaire or the profile feeds
 * it, and how much of it is already theirs. The counts quoted here come from the test route, so the
 * line is only allowed to say what those counts can prove: a section nobody has started cannot be
 * blamed on the partner, and a section the person has finished cannot be offered to them again.
 */
class EmptyBandGapTest {

    private fun band(key: String, label: String) = CategoryScore(key, label, 50, 0.2, hasData = false)

    private fun section(key: String, label: String, answered: Int, total: Int) =
        CategoryProgress(key, label, total, answered)

    @Test
    fun `a band the person has not started is offered as their own work`() {
        val gap = bandGap(band("values", "Ценности"), section("values", "Ценности", 0, 5))
        assertEquals(GapTarget.SECTION, gap.target)
        assertEquals("Пройти раздел", gap.cta)
        assertTrue(gap.line, gap.line.contains("5 ответов"))
        // Nothing of this section is the person's yet, so the partner cannot be named as the gap.
        assertFalse(gap.line, gap.line.contains("партн"))
    }

    @Test
    fun `a band the person is halfway through names both the counts and the missing overlap`() {
        val gap = bandGap(band("leisure", "Досуг"), section("leisure", "Досуг", 2, 5))
        assertEquals(GapTarget.SECTION, gap.target)
        assertEquals("Продолжить раздел", gap.cta)
        assertTrue(gap.line, gap.line.contains("2 ответа из 5"))
        // Half a section is held by the person, so the emptiness is the pair of sets not meeting.
        assertTrue(gap.line, gap.line.contains("не пересеклись"))
    }

    @Test
    fun `a closed section is not offered back to the person`() {
        val gap = bandGap(band("values", "Ценности"), section("values", "Ценности", 5, 5))
        assertEquals(GapTarget.NONE, gap.target)
        assertEquals("", gap.cta)
        // Every card of the section is answered, so a trait of the partner's could not fail to match:
        // the missing side is named, because the counts prove it.
        assertTrue(gap.line, gap.line.contains("5 из 5"))
        assertTrue(gap.line, gap.line.contains("партнёра"))
    }

    @Test
    fun `a band the questionnaire does not measure is sent to the profile`() {
        listOf("interests" to "Интересы", "goals" to "Цель знакомства").forEach { (key, label) ->
            val gap = bandGap(band(key, label), null)
            assertEquals(key, GapTarget.PROFILE, gap.target)
            assertEquals(key, "Заполнить профиль", gap.cta)
            assertTrue(key, gap.line.contains("профил"))
        }
    }

    @Test
    fun `a band with no counts behind it stays inside what is known`() {
        // The progress read did not arrive, so `sections` is empty and a trait band has no numbers:
        // the screen may name the absence, but it may not put a section count on the screen that
        // was never read, nor an action it cannot ground.
        val gap = bandGap(band("communication", "Общение"), null)
        assertEquals(GapTarget.NONE, gap.target)
        assertEquals("", gap.cta)
        assertFalse(gap.line, gap.line.contains("из"))
        assertFalse(gap.line, gap.line.contains("раздел"))
    }

    @Test
    fun `every empty band is described in percents of nothing but the neutral half`() {
        val gaps = listOf(
            bandGap(band("values", "Ценности"), section("values", "Ценности", 0, 5)),
            bandGap(band("values", "Ценности"), section("values", "Ценности", 2, 5)),
            bandGap(band("values", "Ценности"), section("values", "Ценности", 5, 5)),
            bandGap(band("interests", "Интересы"), null),
            bandGap(band("communication", "Общение"), null),
        )
        gaps.forEach { gap ->
            assertTrue(gap.line, gap.line.contains("нейтральных 50%"))
            // A band with no comparison has no measured score, so the line must not print one.
            assertFalse(gap.line, gap.line.contains("нет данных"))
            assertEquals(gap.cta.isNotEmpty(), gap.target != GapTarget.NONE)
        }
    }
}
