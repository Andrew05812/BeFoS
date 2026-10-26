package app.befos.core.designsystem

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The geometry the headline graphic is drawn from, with no renderer in sight.
 *
 * Three claims hold this emblem together, and each is a place where a phone could start telling the pair
 * something the backend did not: the widths are the engine's weights and nothing else; a band the engine
 * did not compare is drawn with nothing in it, whatever number sits on it; and the strip has to stay
 * countable on the smallest screen the app supports and at the largest text a person can set.
 *
 * The last one is the reason [ScoreEmblemGeometry.place] takes a text scale at all. The words around the
 * graphic grow when a person raises it, and a strip that stayed at its dp while the reading grew became a
 * hairline with seven bands nobody could separate — the completeness stopped being visible exactly for the
 * readers who needed the caption least available.
 */
class ScoreEmblemGeometryTest {

    private fun band(
        category: String,
        weight: Double,
        score: Int = 60,
        measured: Boolean = true,
    ) = EmblemBand(
        category = category,
        label = category.replaceFirstChar { it.uppercase() },
        weight = weight,
        score = score,
        measured = measured,
    )

    private val seven = listOf(
        band("values", 0.25),
        band("personality", 0.20),
        band("communication", 0.20),
        band("lifestyle", 0.15),
        band("goals", 0.10),
        band("interests", 0.05, measured = false),
        band("attachment", 0.05),
    )

    @Test
    fun `each band's width is its own weight and the strip adds up to the width it was given`() {
        val slices = ScoreEmblemGeometry.place(seven, widthDp = 411f, textScale = 1f)
        assertEquals(7, slices.size)

        val total = slices.sumOf { it.width.toDouble() } + slices.first().gap * (slices.size - 1)
        assertEquals(
            "seven bands plus their gaps must land on the measure the screen handed over",
            411.0,
            total,
            0.5,
        )
        val heaviest = slices.maxBy { it.width }
        val lightest = slices.minBy { it.width }
        assertEquals("values", heaviest.band.category)
        assertEquals(0.25, heaviest.band.weight, 1e-9)
        // interests and lifestyle both carry 0.05 and 0.15: the ratio between them is the engine's.
        val lifestyle = slices.first { it.band.category == "lifestyle" }.width
        val interests = slices.first { it.band.category == "interests" }.width
        assertEquals(3.0, (lifestyle / interests).toDouble(), 0.01)
        assertTrue("the heaviest band is five times the lightest", lightest.width * 5.0 <= heaviest.width + 0.5)
    }

    @Test
    fun `segments ascend, never overlap, and keep the order the answer sent`() {
        val slices = ScoreEmblemGeometry.place(seven, widthDp = 360f, textScale = 1f)
        assertEquals(seven.map { it.category }, slices.map { it.band.category })
        slices.zipWithNext().forEach { (left, right) ->
            assertTrue(
                "a band must not be drawn on top of its neighbour",
                right.startX >= left.startX + left.width - 1e-3,
            )
        }
        assertTrue(slices.first().startX == 0f)
    }

    @Test
    fun `a band nobody compared is drawn empty whatever number the engine left on it`() {
        // The neutral half is still 50 on the wire. Painting it would put a middling measurement on a band
        // the engine says it never measured, which is the defect this graphic exists not to repeat.
        val quiet = band("interests", 0.2, score = 50, measured = false)
        val slices = ScoreEmblemGeometry.place(listOf(band("values", 0.8), quiet), 400f, 1f)

        assertEquals(0f, slices[1].fillWidth, 1e-6f)
        assertEquals(0f, ScoreEmblemGeometry.fillOf(quiet), 1e-6f)
        assertTrue("the quiet band keeps its full width: the hole is the point", slices[1].width > 0f)
        assertEquals(0.5f, ScoreEmblemGeometry.fillOf(band("values", 0.2, score = 50)), 1e-6f)
    }

    @Test
    fun `the strip stays countable from 320dp up to a 540dp split and at text scale 13`() {
        val scales = listOf(1f, 1.3f)
        listOf(320f, 360f, 411f, 540f).forEach { widthDp ->
            scales.forEach { scale ->
                val slices = ScoreEmblemGeometry.place(seven, widthDp, scale)
                assertEquals(7, slices.size)
                val used = slices.last().startX + slices.last().width
                assertTrue(
                    "$widthDp/$scale overflows the measure it was handed: $used",
                    used <= widthDp + 0.01f,
                )
                slices.forEach { slice ->
                    val floor = ScoreEmblemGeometry.MIN_SLICE_DP.coerceAtMost(widthDp / seven.size)
                    assertTrue(
                        "${slice.band.category} at $widthDp/$scale became ${slice.width}dp — narrower than a gap",
                        slice.width >= floor - 1e-3,
                    )
                }
                // At the scales a person actually picks, the air between bands survives: seven shapes only
                // read as seven while each is still wider than the space beside it.
                if (scale <= 1.3f && widthDp >= 320f) {
                    slices.forEach { assertTrue("gap collapsed at $widthDp/$scale", it.gap > 0f) }
                }
            }
        }
    }

    @Test
    fun `when the width runs out the gaps give way before the bands do`() {
        // 12dp across seven bands cannot hold both floors and gaps. The rule is that the bands survive,
        // because losing a band from the graphic would lose a piece of the pair's completeness.
        val slices = ScoreEmblemGeometry.place(seven, widthDp = 12f, textScale = 1f)
        assertEquals(7, slices.size)
        assertEquals(0f, slices.first().gap, 1e-6f)
        slices.forEach { assertTrue(it.width > 0f) }
        assertEquals(12.0, slices.sumOf { it.width.toDouble() }, 0.01)
    }

    @Test
    fun `shares normalise without inventing a weight, and a strip of none divides equally`() {
        val halves = listOf(band("a", 0.5), band("b", 0.5))
        assertEquals(listOf(0.5f, 0.5f), ScoreEmblemGeometry.shares(halves))
        // Weights that do not sum to 1 are the engine's business; the ratios are what the strip owes.
        val odd = listOf(band("a", 0.3), band("b", 0.1))
        assertEquals(listOf(0.75f, 0.25f), ScoreEmblemGeometry.shares(odd))
        assertEquals(listOf(0.5f, 0.5f), ScoreEmblemGeometry.shares(listOf(band("a", 0.0), band("b", 0.0))))
        assertEquals(
            "a weight the wire should never carry contributes nothing rather than widening its band; " +
                "the band itself is still counted out loud by the caption",
            listOf(0f, 1f),
            ScoreEmblemGeometry.shares(listOf(band("a", -3.0), band("b", 0.4))),
        )
        assertEquals(emptyList<Float>(), ScoreEmblemGeometry.shares(emptyList()))
        assertEquals(emptyList<EmblemSlice>(), ScoreEmblemGeometry.place(emptyList(), 400f, 1f))
        assertEquals(emptyList<EmblemSlice>(), ScoreEmblemGeometry.place(seven, 0f, 1f))
    }

    @Test
    fun `the strip grows with the text instead of thinning against it`() {
        assertTrue(
            ScoreEmblemGeometry.heightForDp(1.3f) > ScoreEmblemGeometry.heightForDp(1f),
        )
        assertEquals(
            ScoreEmblemGeometry.BASE_GAP_DP * 1.3f,
            ScoreEmblemGeometry.place(seven, 411f, 1.3f).first().gap,
            1e-4f,
        )
        // Capped: the emblem is one graphic on a page, not a table that grows with every reading setting.
        assertEquals(
            ScoreEmblemGeometry.BASE_HEIGHT_DP * ScoreEmblemGeometry.MAX_SCALE,
            ScoreEmblemGeometry.heightForDp(9f),
            1e-4f,
        )
    }

    @Test
    fun `the whole graphic is one spoken sentence that names the holes`() {
        val spoken = ScoreEmblemGeometry.spokenDescription(
            percent = 62,
            caption = "сверено 5 из 7 полос",
            quietLabels = listOf("Интересы"),
        )
        assertTrue(spoken.startsWith("Итог 62%."))
        assertTrue(spoken.contains("сверено 5 из 7 полос"))
        assertTrue("the quiet band has to be named, not only drawn", spoken.contains("Интересы"))
        assertTrue("a hole must be announced as a hole", spoken.contains("показаны пустыми"))
        assertEquals(1, spoken.lines().size)

        // Nothing to apologise for when every band was compared, and no caption when the answer had none.
        val plain = ScoreEmblemGeometry.spokenDescription(70, null, emptyList())
        assertEquals("Итог 70%.", plain)
    }

    @Test
    fun `percentages outside the range cannot push a fill past its own band`() {
        assertEquals(1f, ScoreEmblemGeometry.fillOf(band("a", 0.5, score = 140)), 1e-6f)
        assertEquals(0f, ScoreEmblemGeometry.fillOf(band("a", 0.5, score = -20)), 1e-6f)
        val slices = ScoreEmblemGeometry.place(listOf(band("a", 1.0, score = 140)), 200f, 1f)
        assertEquals(200f, slices.single().fillWidth, 0.01f)
    }
}
