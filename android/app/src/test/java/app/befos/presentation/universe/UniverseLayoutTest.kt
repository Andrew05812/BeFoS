package app.befos.presentation.universe

import app.befos.domain.model.Connection
import app.befos.domain.model.UniverseLayer
import app.befos.domain.model.UniverseNode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The geometry the Compatibility Universe draws with. These tests exist because the map must be
 * unable to say something its data does not support: a mark only where its own value puts it, and
 * never a stroke across an answer that was never given.
 */
class UniverseLayoutTest {

    private fun node(
        key: String,
        a: Double?,
        b: Double?,
        connection: Connection,
    ) = UniverseNode(
        key = key,
        label = key,
        aValue = a,
        bValue = b,
        hasData = a != null && b != null,
        connection = connection,
        evidence = "$key: ${a ?: "—"} против ${b ?: "—"}",
        confidence = if (a != null && b != null) 50 else 0,
        suggestion = "$key: договоритесь заранее",
        questions = emptyList(),
    )

    private fun layer(
        category: String,
        nodes: List<UniverseNode>,
        score: Int = 70,
        hasData: Boolean = true,
    ) = UniverseLayer(
        category = category,
        label = category.replaceFirstChar { it.uppercase() },
        score = score,
        weight = 0.14,
        hasData = hasData,
        coverage = if (nodes.isEmpty()) 0.0 else nodes.count { it.hasData }.toDouble() / nodes.size,
        confidence = if (nodes.isEmpty()) 0 else nodes.sumOf { it.confidence } / nodes.size,
        nodes = nodes,
    )

    @Test
    fun `a mark walks toward the shared sky as its own answer rises`() {
        val low = UniverseLayout.markX(leftWorld = true, value = 0.0f)
        val mid = UniverseLayout.markX(leftWorld = true, value = 0.5f)
        val high = UniverseLayout.markX(leftWorld = true, value = 1.0f)
        assertTrue("0.0 must sit nearer the rim than 0.5", low < mid)
        assertTrue("0.5 must sit nearer the rim than 1.0", mid < high)
        // The highest answer still stops short of the world's rim on the far side.
        assertTrue(high < UniverseLayout.WORLD_B_CENTER_X)
    }

    @Test
    fun `the two worlds mirror each other`() {
        assertEquals(
            UniverseLayout.markX(true, 0.8f).toDouble(),
            (1f - UniverseLayout.markX(false, 0.8f)).toDouble(),
            1e-5,
        )
    }

    @Test
    fun `a value that should not exist cannot push a mark off the map`() {
        assertEquals(
            UniverseLayout.markX(true, 1f).toDouble(),
            UniverseLayout.markX(true, 42f).toDouble(),
            1e-5,
        )
        assertEquals(
            UniverseLayout.markX(true, 0f).toDouble(),
            UniverseLayout.markX(true, -7f).toDouble(),
            1e-5,
        )
    }

    @Test
    fun `an uncomparable node gets one mark and no stroke`() {
        val bands = UniverseLayout.place(
            listOf(
                layer(
                    "values",
                    listOf(
                        node("both", 0.8, 0.2, Connection.DISCUSSION),
                        node("only_a", 0.7, null, Connection.UNKNOWN),
                        node("only_b", null, 0.3, Connection.UNKNOWN),
                    ),
                ),
            ),
        )
        val placements = bands.single().placements
        assertEquals(2, placements.first { it.node.key == "both" }.marks.size)
        val onlyA = placements.first { it.node.key == "only_a" }
        assertEquals(listOf(UniverseLayout.Side.A), onlyA.marks.map { it.side })
        assertEquals(UniverseLayout.LinkStyle.NONE, onlyA.link)
        val onlyB = placements.first { it.node.key == "only_b" }
        assertEquals(listOf(UniverseLayout.Side.B), onlyB.marks.map { it.side })
        assertEquals(UniverseLayout.LinkStyle.NONE, onlyB.link)
    }

    @Test
    fun `unknown is never drawn as a meeting even when both sides answered`() {
        // The server can mark a node unknown while still naming one side; the client must not
        // promote that to a line across the map.
        val bands = UniverseLayout.place(listOf(layer("goals", listOf(node("goal", 0.5, 0.5, Connection.UNKNOWN)))))
        assertEquals(UniverseLayout.LinkStyle.NONE, bands.single().placements.single().link)
    }

    @Test
    fun `each connection type keeps its own shape and its own stroke`() {
        val expected = mapOf(
            Connection.HARMONY to UniverseLayout.LinkStyle.SOLID,
            Connection.COMPLEMENTARITY to UniverseLayout.LinkStyle.DASHED,
            Connection.DISCUSSION to UniverseLayout.LinkStyle.BROKEN,
            Connection.UNKNOWN to UniverseLayout.LinkStyle.NONE,
        )
        val shapes = expected.keys.map { UniverseLayout.shapeOf(it) }.toSet()
        assertEquals("four types, four shapes", 4, shapes.size)
        expected.forEach { (kind, link) ->
            assertEquals("link for $kind", link, UniverseLayout.linkOf(kind, bothSides = true))
            // a missing second answer always wins over the type: nothing to connect
            assertEquals(
                "one-sided $kind",
                UniverseLayout.LinkStyle.NONE,
                UniverseLayout.linkOf(kind, bothSides = false),
            )
        }
    }

    @Test
    fun `every node gets its own row and the bands keep the server order`() {
        val layers = listOf(
            layer("values", (1..5).map { node("v$it", 0.5, 0.5, Connection.HARMONY) }),
            layer("personality", (1..3).map { node("p$it", 0.5, 0.5, Connection.HARMONY) }),
            layer("interests", emptyList(), score = 0, hasData = false),
        )
        val bands = UniverseLayout.place(layers)
        assertEquals(layers.map { it.category }, bands.map { it.layer.category })
        assertEquals(5, bands[0].placements.size)
        assertEquals(3, bands[1].placements.size)
        assertTrue("a band without nodes still gets its caption row", bands[2].placements.isEmpty())
        assertEquals(
            "one caption row plus one row per node, and an empty band still costs a caption row",
            5 + 1 + 3 + 1 + 1 + 1,
            UniverseLayout.rowCount(layers),
        )
        assertEquals(
            (UniverseLayout.rowCount(layers) * UniverseLayout.ROW_DP).toDouble(),
            UniverseLayout.heightForDp(layers).toDouble(),
            1e-4,
        )
        bands.zipWithNext().forEach { (first, second) ->
            assertTrue("bands must not overlap", first.bottom <= second.top + 1e-6)
            assertTrue(second.labelY > second.top)
        }
        val ys = bands[0].placements.map { it.y }
        assertEquals("rows ascend", ys.sorted(), ys)
        assertEquals(
            "rows are evenly pitched",
            1.0,
            ((ys[1] - ys[0]) / (ys[2] - ys[1])).toDouble(),
            1e-4,
        )
    }

    @Test
    fun `the map carries the layer object instead of recomputing its numbers`() {
        val source = layer("lifestyle", listOf(node("smoking", 0.9, 0.1, Connection.DISCUSSION)), score = 41)
        val band = UniverseLayout.place(listOf(source)).single()
        assertSame(source, band.layer)
        assertEquals(41, band.layer.score)
        val mark = band.placements.single().marks.first { it.side == UniverseLayout.Side.A }
        assertEquals(90, mark.percent)
    }

    @Test
    fun `a tap finds the nearest mark and ignores empty space`() {
        val bands = UniverseLayout.place(
            listOf(
                layer(
                    "values",
                    listOf(
                        node("a", 1.0, 1.0, Connection.HARMONY),
                        node("b", 0.0, 0.0, Connection.DISCUSSION),
                    ),
                ),
            ),
        )
        val placement = bands.single().placements.first { it.node.key == "a" }
        val mark = placement.marks.first()
        val heightDp = UniverseLayout.heightForDp(bands.map { it.layer })
        val aspect = 420f / heightDp
        assertNotNull(
            UniverseLayout.nodeAt(bands, x = mark.x, y = placement.y, aspect = aspect, heightDp = heightDp),
        )
        // far to the left of the leftmost mark, outside the touch tolerance
        assertNull(
            UniverseLayout.nodeAt(bands, x = 0.001f, y = placement.y, aspect = aspect, heightDp = heightDp),
        )
    }

    @Test
    fun `percent and gap follow the values the node itself shows`() {
        assertEquals(75, UniverseLayout.percentOf(0.749f))
        assertNull(UniverseLayout.percentOf(null))
        val near = node("near", 0.9, 0.9, Connection.HARMONY)
        val far = node("far", 0.1, 0.1, Connection.DISCUSSION)
        assertTrue(UniverseLayout.gapOf(near)!! < UniverseLayout.gapOf(far)!!)
        assertNull(UniverseLayout.gapOf(node("half", 0.5, null, Connection.UNKNOWN)))
    }

    @Test
    fun `a mark carries the answer it was drawn for, not its own coordinate`() {
        val bands = UniverseLayout.place(
            listOf(layer("values", listOf(node("spending", 0.9, 0.1, Connection.DISCUSSION))))
        )
        val marks = bands.single().placements.single().marks
        val left = marks.first { it.side == UniverseLayout.Side.A }
        val right = marks.first { it.side == UniverseLayout.Side.B }
        // The x lives inside the world's inset: read back as a percent it labels a 0.9 answer with a
        // number nobody answered, which is the defect this test was written for.
        assertEquals(90, left.percent)
        assertEquals(10, right.percent)
    }

    @Test
    fun `every mark stays its own node on a 320dp phone and on a 540dp split`() {
        val layers = listOf(
            layer("values", (1..4).map { node("v$it", it / 4.0, (5 - it) / 4.0, Connection.DISCUSSION) }),
            layer("lifestyle", listOf(node("smoking", 1.0, 1.0, Connection.HARMONY))),
            layer(
                "interests",
                listOf(node("music", 1.0, 1.0, Connection.HARMONY), node("cooking", 0.0, null, Connection.UNKNOWN)),
            ),
        )
        val bands = UniverseLayout.place(layers)
        val heightDp = UniverseLayout.heightForDp(layers)
        // 20dp screen gutter + 16dp card padding on each side, and the canvas never grows past 420dp.
        listOf(320f, 360f, 411f, 540f).forEach { screenDp ->
            val canvasDp = minOf(420f, screenDp - 72f)
            val aspect = canvasDp / heightDp
            bands.flatMap { it.placements }.forEach { placement ->
                placement.marks.forEach { mark ->
                    assertEquals(
                        "${placement.node.key} at ${canvasDp}dp canvas",
                        placement.node.key,
                        UniverseLayout.nodeAt(
                            bands = bands,
                            x = mark.x,
                            y = mark.y,
                            aspect = aspect,
                            toleranceDp = 26f,
                            heightDp = heightDp,
                        )?.key,
                    )
                }
            }
        }
    }

    @Test
    fun `an empty map places nothing and stays a legal height`() {
        assertEquals(emptyList<Any>(), UniverseLayout.place(emptyList()))
        assertEquals(0, UniverseLayout.rowCount(emptyList()))
        assertTrue(UniverseLayout.heightForDp(emptyList()) > 0f)
        assertFalse(UniverseLayout.place(emptyList()).any())
    }
}
