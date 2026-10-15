package app.befos.presentation.common

import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The line an empty band prints, and the action it offers.
 *
 * «нет данных» under a bar answers the question «was this measured» and leaves the next one open: a
 * person who wants that band filled has to find out whether the questionnaire or the profile feeds
 * it, and how much of it is already theirs. The counts quoted here come from the test route, so the
 * line is only allowed to say what those counts can prove: a section nobody has started cannot be
 * blamed on the other side, and a section the person has finished cannot be offered to them again.
 *
 * The same sentences go to two screens — the pair page and the card of a person from the deck — so
 * these checks sit beside the function that writes them, not beside either screen.
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
        // Nothing of this section is the person's yet, so the other side cannot be named as the gap.
        assertFalse(gap.line, gap.line.contains("партн"))
        assertFalse(gap.line, gap.line.contains("этого человека"))
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
        // Every card of the section is answered, so a trait of the other side could not fail to
        // match: the missing answers are named, because the counts prove it.
        assertTrue(gap.line, gap.line.contains("5 из 5"))
        assertTrue(gap.line, gap.line.contains("нет ответов"))
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

    @Test
    fun `a pair names the other side of a gap by the route it arrived on`() {
        // Two bands are the only ones that speak about the other questionnaire, and both take the
        // word from the screen: the pair page holds a partner, and saying so is true there.
        val halves = bandGap(band("leisure", "Досуг"), section("leisure", "Досуг", 2, 5))
        assertTrue(halves.line, halves.line.contains("ответами партнёра"))
        val closed = bandGap(band("values", "Ценности"), section("values", "Ценности", 5, 5))
        assertTrue(closed.line, closed.line.contains("нет ответов партнёра"))
    }

    @Test
    fun `a card from the deck does not claim a pair that was never made`() {
        val peer = "этого человека"
        val halves = bandGap(band("leisure", "Досуг"), section("leisure", "Досуг", 2, 5), peer)
        assertTrue(halves.line, halves.line.contains("ответами этого человека"))
        assertFalse(halves.line, halves.line.contains("партн"))

        val closed = bandGap(band("values", "Ценности"), section("values", "Ценности", 5, 5), peer)
        assertTrue(closed.line, closed.line.contains("нет ответов этого человека"))
        assertFalse(closed.line, closed.line.contains("партн"))

        // The other four sentences never named the second questionnaire, so the word changes
        // nothing about them — the actions and the counts stay the ones the pair screen offers.
        listOf(
            bandGap(band("values", "Ценности"), section("values", "Ценности", 0, 5), peer),
            bandGap(band("interests", "Интересы"), null, peer),
            bandGap(band("communication", "Общение"), null, peer),
        ).forEach { gap -> assertFalse(gap.line, gap.line.contains("партн")) }
        assertEquals("Пройти раздел", bandGap(band("values", "Ценности"), section("values", "Ценности", 0, 5), peer).cta)
        assertEquals(GapTarget.PROFILE, bandGap(band("interests", "Интересы"), null, peer).target)
    }
}
