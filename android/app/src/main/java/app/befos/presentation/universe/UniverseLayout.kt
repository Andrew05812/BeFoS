package app.befos.presentation.universe

import app.befos.domain.model.Connection
import app.befos.domain.model.UniverseLayer
import app.befos.domain.model.UniverseNode
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.roundToInt
import kotlin.math.sqrt

/**
 * Geometry of the Compatibility Universe, kept out of Compose so it can be tested without a
 * device and read without a renderer.
 *
 * Everything is expressed in a unit square (0f..1f): the screen multiplies by its own size.
 * Two shapes are the two worlds of the pair, in the pair's own order (`a` left, `b` right) — the
 * same order the server answered with, so both partners open one map, not two mirrored ones.
 * A node gets one row, and inside each world its mark sits at the distance that node's own value
 * puts it: an answer of 1f reaches toward the shared sky in the middle, an answer of 0f stays on
 * that world's side. Nothing here computes a number — the positions read the values the node
 * already displays, so a mark can never sit somewhere its evidence does not explain.
 */
object UniverseLayout {

    const val WORLD_A_CENTER_X = 0.26f
    const val WORLD_B_CENTER_X = 0.74f
    const val WORLD_CENTER_Y = 0.5f
    const val WORLD_RADIUS = 0.24f

    /** How far from a world's centre a mark may travel, leaving the rim clear for the caption. */
    private const val INSET = 0.17f

    /** The strip above the bands holds the two world captions. */
    const val NAMES_BOTTOM = 0.042f
    const val BANDS_TOP = 0.055f
    const val BANDS_BOTTOM = 0.975f

    /** Rows are laid out at this pitch, so a mark stays inside a comfortable touch target. */
    const val ROW_DP = 30f

    enum class Side { A, B }

    /** Four connection types, four shapes: the map reads in grayscale and with colour-blindness. */
    enum class MarkShape { DOT, RING, DIAMOND, ABSENCE }

    /** How the stroke between two marks is drawn. `NONE` is what an unknown node gets. */
    enum class LinkStyle { SOLID, DASHED, BROKEN, NONE }

    data class Mark(
        val side: Side,
        val x: Float,
        val y: Float,
        val shape: MarkShape,
        /** Percent this mark stands at, or null when this side never answered. */
        val percent: Int?,
    )

    data class Placement(
        val node: UniverseNode,
        val layer: UniverseLayer,
        val y: Float,
        val marks: List<Mark>,
        val link: LinkStyle,
    )

    data class Band(
        val layer: UniverseLayer,
        val top: Float,
        val bottom: Float,
        /** The row that carries this band's caption, above its first node. */
        val labelY: Float,
        val placements: List<Placement>,
    )

    /** Percent a value sits at, rounded the way the screen already rounds percents. */
    fun percentOf(value: Float?): Int? = value?.let { (value * 100f).roundToInt() }

    /**
     * Distance between the two marks of a node, in unit space. Only defined for compared nodes:
     * an unknown node has one mark, so the map draws no meeting and no gap either.
     */
    fun gapOf(node: UniverseNode): Float? {
        val a = node.aValue ?: return null
        val b = node.bValue ?: return null
        return abs(markX(true, a.toFloat()) - markX(false, b.toFloat()))
    }

    fun markX(leftWorld: Boolean, value: Float): Float {
        val v = value.coerceIn(0f, 1f)
        return if (leftWorld) {
            WORLD_A_CENTER_X - INSET + v * 2f * INSET
        } else {
            WORLD_B_CENTER_X + INSET - v * 2f * INSET
        }
    }

    fun shapeOf(connection: Connection): MarkShape = when (connection) {
        Connection.HARMONY -> MarkShape.DOT
        Connection.COMPLEMENTARITY -> MarkShape.RING
        Connection.DISCUSSION -> MarkShape.DIAMOND
        Connection.UNKNOWN -> MarkShape.ABSENCE
    }

    fun linkOf(connection: Connection, bothSides: Boolean): LinkStyle = when {
        !bothSides || connection == Connection.UNKNOWN -> LinkStyle.NONE
        connection == Connection.HARMONY -> LinkStyle.SOLID
        connection == Connection.COMPLEMENTARITY -> LinkStyle.DASHED
        else -> LinkStyle.BROKEN
    }

    /** How many rows the map needs: one caption row per band plus one row per node. */
    fun rowCount(layers: List<UniverseLayer>): Int =
        layers.sumOf { 1 + max(1, it.nodes.size) }

    /** Canvas height in dp that keeps every row at [ROW_DP] pitch. */
    fun heightForDp(layers: List<UniverseLayer>): Float =
        max(1, rowCount(layers)) * ROW_DP

    fun place(layers: List<UniverseLayer>, gapRows: Float = 0.5f): List<Band> {
        if (layers.isEmpty()) return emptyList()
        val span = BANDS_BOTTOM - BANDS_TOP
        val rowCounts = layers.map { 1 + max(1, it.nodes.size) }
        val totalRows = rowCounts.sum() + gapRows * (layers.size - 1)
        val row = span / totalRows
        var cursor = BANDS_TOP
        return layers.mapIndexed { index, layer ->
            if (index > 0) cursor += gapRows * row
            val top = cursor
            val labelY = top + row / 2f
            cursor = top + rowCounts[index] * row
            Band(
                layer = layer,
                top = top,
                bottom = cursor,
                labelY = labelY,
                placements = layer.nodes.mapIndexed { nodeIndex, node ->
                    val y = labelY + row * (nodeIndex + 1)
                    val ax = node.aValue?.let { markX(true, it.toFloat()) }
                    val bx = node.bValue?.let { markX(false, it.toFloat()) }
                    val marks = buildList {
                        // The percent a mark carries is the answered value, not the place it was
                        // drawn at: the x is squeezed into the world's inset, so reading it back
                        // as a number would label a 0.9 answer with its own coordinate.
                        ax?.let {
                            add(Mark(Side.A, it, y, shapeOf(node.connection), percentOf(node.aValue?.toFloat())))
                        }
                        bx?.let {
                            add(Mark(Side.B, it, y, shapeOf(node.connection), percentOf(node.bValue?.toFloat())))
                        }
                    }
                    Placement(
                        node = node,
                        layer = layer,
                        y = y,
                        marks = marks,
                        link = linkOf(node.connection, ax != null && bx != null),
                    )
                },
            )
        }
    }

    /**
     * The node whose mark owns this tap, or null. Distance is measured in unit space against the
     * canvas aspect the screen actually drew with, so [aspect] (width / height) keeps the
     * tolerance round instead of a vertical ellipse.
     */
    fun nodeAt(
        bands: List<Band>,
        x: Float,
        y: Float,
        aspect: Float,
        toleranceDp: Float = 22f,
        heightDp: Float = 1f,
    ): UniverseNode? {
        val tolerance = toleranceDp / max(1f, heightDp)
        var best: UniverseNode? = null
        var bestDistance = Float.MAX_VALUE
        bands.forEach { band ->
            band.placements.forEach { placement ->
                placement.marks.forEach { mark ->
                    val dx = (x - mark.x) * aspect
                    val dy = y - mark.y
                    val distance = sqrt(dx * dx + dy * dy)
                    if (distance <= tolerance && distance < bestDistance) {
                        bestDistance = distance
                        best = placement.node
                    }
                }
            }
        }
        return best
    }
}
