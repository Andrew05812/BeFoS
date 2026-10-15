package app.befos.presentation.common

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The seven bands a pair is shown are an average of two people's answers, and the screen under them
 * used to be the only place that said so — the public profile of another person printed the same
 * list, with the same «важность» in every row and the same «нет данных», and no word at all about
 * what its numbers measure. A reader who came from a Discovery card could take 78 on her band for a
 * trait of hers, when the engine built that 78 from my answers against hers.
 *
 * So the caption is one function, and these tests hold the three things it has to do at once: name
 * the unit the percent is written in, deny that it belongs to one person, and explain the second
 * number the rows carry. It quotes the word [categoryReadout] prints for an unmeasured band instead
 * of spelling a variant of it, and it holds no digit of its own — a caption that printed a percent
 * would compete with the percents above it.
 */
class PairBandsCaptionTest {

    private val caption = pairBandsCaption()

    @Test
    fun `the caption names its number as the similarity of two questionnaires`() {
        assertTrue(
            "the caption does not say the percent is a similarity of two answers: $caption",
            caption.contains("сходство двух анкет"),
        )
    }

    @Test
    fun `the caption denies that a band measures one person`() {
        // The whole defect this stage exists for is the reading the caption has to rule out.
        assertTrue(
            "the caption leaves a band reading like one person's trait: $caption",
            caption.contains("не черта одного человека"),
        )
    }

    @Test
    fun `the caption explains the importance the rows print`() {
        // CategoryScoreRow writes "важность N%" above a band whenever the engine sent a weight.
        assertTrue(
            "the caption never mentions the word its own rows put on screen: $caption",
            caption.contains("важность"),
        )
        assertTrue(
            "the caption leaves «важность» unexplained while naming the total it feeds: $caption",
            caption.lowercase().contains("итог"),
        )
    }

    @Test
    fun `the caption quotes the word an unmeasured band actually prints`() {
        // Two spellings of the same absence would mean the caption describes a list it is not under.
        assertTrue(
            "the caption names an absence the rows do not print: $caption",
            caption.contains(categoryReadout(hasData = false, score = 50)),
        )
    }

    @Test
    fun `the caption carries no digit of its own`() {
        caption.forEach { ch ->
            assertFalse(
                "a caption that prints a number competes with the numbers it captions: $caption",
                ch.isDigit(),
            )
        }
    }
}
