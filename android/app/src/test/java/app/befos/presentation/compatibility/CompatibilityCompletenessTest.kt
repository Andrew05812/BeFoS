package app.befos.presentation.compatibility

import app.befos.core.designsystem.EmblemBand
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Compatibility
import app.befos.domain.model.Connection
import app.befos.domain.model.Explanation
import app.befos.presentation.common.bandUnmeasuredWord
import app.befos.presentation.common.categoryReadout
import app.befos.presentation.common.categorySpoken
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The sentences the pair's compatibility screen puts on the engine's numbers.
 *
 * Every one of these exists to say less than the data, not more: the completeness line reports the two
 * counts the answer carries, the weight line reports the fraction it carries, and the per-band words quote
 * the absence the rows already print instead of spelling a new one. A screen that rounded the pair's
 * completeness up, or called an unmeasured band a low band, would be the phone agreeing with itself about
 * two people's answers — which is the class of defect this page has been reworked to stop being able to
 * commit.
 */
class CompatibilityCompletenessTest {

    private fun compatibility(
        measured: Int? = 5,
        total: Int? = 7,
        weight: Double? = 0.85,
        categories: List<CategoryScore> = listOf(
            CategoryScore("values", "Ценности", 88, 0.25),
            CategoryScore("interests", "Интересы", 50, 0.05, hasData = false),
        ),
    ) = Compatibility(
        overall = 62,
        categories = categories,
        strengths = emptyList(),
        differences = emptyList(),
        sharedInterests = emptyList(),
        engineVersion = 3,
        bandsMeasured = measured,
        bandsTotal = total,
        measuredWeight = weight,
        starter = "",
    )

    @Test
    fun `the caption states the completeness the server named, in the words the screen promises`() {
        assertEquals("сверено 5 из 7 полос", completenessCaption(5, 7))
        assertEquals("сверено 1 из 7 полос", completenessCaption(1, 7))
        assertEquals("сверено 7 из 7 полос", completenessCaption(7, 7))
    }

    @Test
    fun `one band is named in the case the sentence actually needs`() {
        assertEquals("сверено 1 из 1 полосы", completenessCaption(1, 1))
        assertEquals("полос", bandsWord(7))
        assertEquals("полосы", bandsWord(1))
    }

    @Test
    fun `a result standing only on the neutral half is said out loud`() {
        // This is the case a reader must not have to notice by themselves: the percent is not a measurement
        // of anything at that point, and the engine says so.
        assertEquals("ни одна из 7 полос не сверена", completenessCaption(0, 7))
    }

    @Test
    fun `an answer that reported no completeness gets no caption rather than an invented one`() {
        assertNull(completenessCaption(null, null))
        assertNull(completenessCaption(5, null))
        assertNull(completenessCaption(null, 7))
        // Zero bands total is not «0 из 0»: it is the answer saying nothing about bands at all.
        assertNull(completenessCaption(0, 0))
    }

    @Test
    fun `the weight line repeats the engine's own share and never a share of its own`() {
        assertEquals("сравнённые полосы покрывают 85% веса итога", measuredWeightCaption(0.85))
        assertEquals("сравнённые полосы покрывают 100% веса итога", measuredWeightCaption(1.0))
        assertNull(measuredWeightCaption(null))
        assertNull(measuredWeightCaption(Double.NaN))
    }

    @Test
    fun `the emblem's bands are the engine's weights and the engine's flag, in the engine's order`() {
        val categories = listOf(
            CategoryScore("values", "Ценности", 88, 0.25),
            CategoryScore("lifestyle", "Уклад", 50, 0.15, hasData = false),
            CategoryScore("interests", "Интересы", 50, 0.05, hasData = false),
        )

        assertEquals(
            listOf(
                EmblemBand("values", "Ценности", 0.25, 88, measured = true),
                EmblemBand("lifestyle", "Уклад", 0.15, 50, measured = false),
                EmblemBand("interests", "Интересы", 0.05, 50, measured = false),
            ),
            emblemBands(categories),
        )
        // A band nobody answered keeps the neutral half it carries on the wire and loses it in the drawing:
        // `measured` is the flag the strip holes itself on, not the number beside it.
        assertEquals(listOf("Уклад", "Интересы"), quietBandLabels(categories))
    }

    @Test
    fun `the graphic is spoken as one sentence that carries the same counts it draws`() {
        val spoken = emblemSpoken(compatibility())

        assertTrue(spoken.contains("Итог 62%"))
        assertTrue(spoken.contains("сверено 5 из 7 полос"))
        assertTrue("a hole the eye is shown has to be named to the ear", spoken.contains("Интересы"))
        assertEquals(1, spoken.lines().size)
    }

    @Test
    fun `a document that named no completeness is spoken without inventing one`() {
        val spoken = emblemSpoken(compatibility(measured = null, total = null, weight = null))

        assertTrue(spoken.contains("Итог 62%"))
        assertTrue("the sentence may not claim a completeness the answer did not send", !spoken.contains("сверено"))
    }

    @Test
    fun `the three kinds of difference are three different words and none of them is a verdict`() {
        val words = listOf(
            Connection.HARMONY,
            Connection.COMPLEMENTARITY,
            Connection.DISCUSSION,
        ).map { explanationKindWord(it) }

        assertEquals(3, words.toSet().size)
        words.forEach { assertTrue("kind word missing: $it", !it.isNullOrBlank()) }
        // A difference is not an error: the screen's own hint for the sharpest kind has to say so.
        assertTrue(explanationKindHint(Connection.DISCUSSION).contains("не ошибка"))
    }

    @Test
    fun `an explanation the engine never classified is left unclassified`() {
        assertNull(explanationKindWord(Connection.UNKNOWN))
        // The label travels alone rather than picking up a kind this build invented.
        assertEquals("Ценности", kindLine(Explanation("values", "Ценности", "текст", 0.88)))
        assertEquals(
            "Ценности · совпадение",
            kindLine(Explanation("values", "Ценности", "текст", 0.88, Connection.HARMONY)),
        )
    }

    @Test
    fun `an unmeasured band is told as unmeasured, in the words its own row prints`() {
        val quiet = CategoryScore("interests", "Интересы", 50, 0.05, hasData = false)
        val measured = CategoryScore("values", "Ценности", 88, 0.25)
        val spoken = categorySpoken(quiet, expandable = true)

        // One spelling of the same absence, quoted from the row rather than paraphrased under it: the
        // panel has to say what the row above it says, in the same words.
        assertTrue(bandMeasuredWord(quiet).contains(categoryReadout(hasData = false, score = 50)))
        assertTrue(bandMeasuredWord(quiet).contains(bandUnmeasuredWord()))
        assertTrue(
            "the row and the panel told the same band two different things: «$spoken» / «${bandMeasuredWord(quiet)}»",
            spoken.contains(bandUnmeasuredWord()),
        )
        assertTrue(bandMeasuredWord(measured).contains("сверена"))
    }

    @Test
    fun `the meaning of a band is the engine's own line about that band, or the silence about it`() {
        val values = CategoryScore("values", "Ценности", 88, 0.25)
        val lines = listOf(
            Explanation("values", "Ценности", "Похожее отношение: семья", 0.88, Connection.HARMONY),
            Explanation("lifestyle", "Уклад", "Разное отношение: ритм сна", 0.2, Connection.DISCUSSION),
        )

        assertEquals(listOf("Похожее отношение: семья"), bandMeaning(values, lines))
        assertEquals(emptyList<String>(), bandMeaning(CategoryScore("goals", "Цели", 50, 0.1), lines))
        assertTrue(bandMeaningAbsenceWord(values).contains("ни одной причины"))
        assertTrue(bandMeaningAbsenceWord(CategoryScore("goals", "Цели", 50, 0.1, hasData = false)).isNotBlank())
    }

    @Test
    fun `the hint about holes appears only while there are holes`() {
        assertNull(quietBandsHint(listOf(CategoryScore("values", "Ценности", 88, 0.25))))
    }

    @Test
    fun `the hint about holes agrees in number with the holes it counts`() {
        val one = quietBandsHint(
            listOf(
                CategoryScore("values", "Ценности", 88, 0.25),
                CategoryScore("interests", "Интересы", 50, 0.05, hasData = false),
            ),
        )!!
        // Одна дыра не может называться «они показаны пустыми»: экран говорит об одной полосе.
        assertTrue(one.contains("полоса"))
        assertTrue(one.contains("она показана пустой"))
        assertTrue("единственная полоса не считается списком", !one.contains("полос:"))
        assertTrue(!one.contains("они"))

        val two = quietBandsHint(
            listOf(
                CategoryScore("interests", "Интересы", 50, 0.05, hasData = false),
                CategoryScore("leisure", "Досуг", 50, 0.05, hasData = false),
            ),
        )!!
        assertTrue(two.contains("Не сверено полос: 2"))
        assertTrue(two.contains("они показаны пустыми"))
    }
}
