package app.befos.presentation.discovery

import app.befos.domain.model.OutgoingLike
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The score line of a row on the account's own list of taps, measured where it is actually drawn.
 *
 * The phrase «Совместимость 62%» used to sit in the column between the avatar and the withdraw button,
 * which on a 320dp phone leaves fewer dp than the single word «Совместимость». A line narrower than one of
 * its words leaves the text system only one way out — it breaks inside the word — and the row then reads
 * «Совмести» / «мость 62%». The fix is the layout's, not the sentence's: the percent is a fact about a tap
 * the account made, and abbreviating it to fit would be quietly removing it.
 *
 * The estimate below is the honest part of a JVM test that cannot ask a layout pass: it is deliberately
 * generous on the advance of a Cyrillic letter and includes the letter spacing the Overline style carries,
 * so a phrase this says fits has room left over, and a phrase it says does not fit was never going to.
 */
class MyLikesScoreLineTest {

    private fun like(percent: Int?) = OutgoingLike(
        userId = "u1",
        name = "Аня",
        age = 27,
        city = "Москва",
        photoUrl = null,
        compatibility = percent,
        likedAt = "2026-10-01T10:00:00+03:00",
    )

    @Test
    fun `the line is drawn on the card's whole interior rather than in the column beside the button`() {
        assertEquals(248f, myLikesScoreSlotDp(320f), 0.01)
        assertEquals(288f, myLikesScoreSlotDp(360f), 0.01)
        // The slot the row used to give it: the same interior minus the avatar, the row's two gaps and the
        // withdraw button. One word of the phrase does not fit in it, and that is the whole defect.
        val squeezed = myLikesScoreSlotDp(320f) - 44f - 2f * 12f - 104f
        assertTrue(
            "the old slot ($squeezed dp) was wide enough after all: the word would not have broken",
            squeezed < myLikesWordWidthDp("Совместимость 62%", 1f),
        )
    }

    @Test
    fun `the phrase never has to break inside a word on any supported width`() {
        listOf(320f, 360f, 411f, 540f).forEach { width ->
            listOf(1f, 1.15f, 1.3f, 2f).forEach { scale ->
                listOf(0, 62, 100).forEach { percent ->
                    assertTrue(
                        "$percent% at ${width}dp/${scale}: word ${myLikesWordWidthDp(myLikesScoreWord(like(percent)), scale)} " +
                            "does not fit ${myLikesScoreSlotDp(width)}",
                        myLikesScoreFits(like(percent), width, scale),
                    )
                }
            }
        }
    }

    @Test
    fun `the sentence that replaces a missing percent is held to the same rule`() {
        // «Процент не записан» is the longer phrase, and it shares the same line.
        assertTrue(myLikesWordWidthDp(myLikesScoreWord(like(null)), 1.3f) > myLikesWordWidthDp("62%", 1.3f))
        listOf(320f, 360f, 411f, 540f).forEach { width ->
            assertTrue(myLikesScoreFits(like(null), width, 1.3f))
            assertTrue(myLikesScoreFits(like(null), width, 2f))
        }
        assertFalse(myLikesScoreFits(like(62), 320f, 6f))
    }

    @Test
    fun `the wording itself is unchanged, so the row still says what it measured`() {
        assertEquals("Совместимость 62%", myLikesScoreWord(like(62)))
        assertEquals("Процент не записан", myLikesScoreWord(like(null)))
    }

    private fun assertEquals(expected: Float, actual: Float, delta: Double) =
        org.junit.Assert.assertEquals(expected.toDouble(), actual.toDouble(), delta)
}
