package app.befos.core.designsystem

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import kotlin.math.max

/**
 * The headline graphic of the pair's compatibility: one segment per band, as wide as that band's own
 * weight, and filled as far as the engine measured it.
 *
 * It exists because a single percent cannot say what it rests on. Two pairs can both read 62 % while
 * one of them has all seven bands compared and the other has five compared and two neutral halves, and a
 * ring — [CompatibilityScore], which draws one number and nothing else — shows the same arc for both.
 * Here the completeness is in the body of the graphic: a band nobody answered keeps its full width and
 * gets the quiet treatment, so an absence is a shape on the strip rather than a caption under it that a
 * reader may or may not connect to the number above.
 *
 * Nothing in this file computes a score, a weight or a threshold. [EmblemBand] arrives with the numbers
 * the engine wrote; the widths come from those weights alone; a band is drawn empty exactly when the
 * answer said it was not compared, never because a number on the device looked too low. It is
 * deliberately not a circular progress indicator: the seven parts have to be countable, and an arc whose
 * segments are hairline-thin at the top of a phone is not.
 */

/** One band, as the emblem needs it: what it is called, how heavy it is, and how much of it was measured. */
data class EmblemBand(
    val category: String,
    val label: String,
    /** The engine's weight for this band, carried here untouched. */
    val weight: Double,
    /** The band's own percent: only ever used to pick the fill's hue and to name the band out loud. */
    val score: Int,
    /** False means the engine compared nothing here. The segment says so instead of being filled. */
    val measured: Boolean,
)

/** Where one band's segment lands inside the drawn strip, in dp from its left edge. */
data class EmblemSlice(
    val band: EmblemBand,
    val startX: Float,
    val width: Float,
    /** The measured part of this segment, in dp — zero for a band that was not compared. */
    val fillWidth: Float,
    /** The space left between this segment and the next one, in dp. */
    val gap: Float,
)

/**
 * The geometry, kept apart from Compose so it can be read and tested without a renderer.
 *
 * [shares] normalises the engine's weights into shares of the whole strip; [place] turns shares into dp
 * for the width the caller actually has and the text scale the person actually reads at. The order is the
 * answer's own — the emblem never re-sorts the bands, so the strip and the list under it describe the
 * same pair in the same sequence.
 */
object ScoreEmblemGeometry {

    /** The space between two segments at the default text scale: enough to count seven bands. */
    const val BASE_GAP_DP = 2f

    /**
     * A segment narrower than this cannot be told apart from the gap beside it, so [place] gives up its
     * gaps before it gives up a band: seven counts only if all seven are still visible.
     */
    const val MIN_SLICE_DP = 3f

    /** The strip's height at the default scale; it grows with the text so it never becomes a hairline. */
    const val BASE_HEIGHT_DP = 14f

    /** How far the text scale may stretch the strip's proportions. Capped — it is one graphic, not a table. */
    const val MAX_SCALE = 2f

    /**
     * Shares of the strip, in the order the bands arrived.
     *
     * The weights come from the engine and are only ever normalised here: the ratio between two bands is
     * theirs, not this file's. A weight that is negative, missing or not a number counts as zero rather
     * than as a wider band, and when no band carries a weight the strip divides equally — seven invisible
     * bands is a worse answer than seven equal ones.
     */
    fun shares(bands: List<EmblemBand>): List<Float> {
        if (bands.isEmpty()) return emptyList()
        val usable = bands.map { it.weight.takeIf { w -> w.isFinite() && w > 0.0 } ?: 0.0 }
        val sum = usable.sum()
        if (sum <= 0.0) return List(bands.size) { 1f / bands.size }
        return usable.map { (it / sum).toFloat() }
    }

    /** The fraction of its own segment a band fills: the band's percent, or nothing when it was not compared. */
    fun fillOf(band: EmblemBand): Float =
        if (!band.measured) 0f else band.score.coerceIn(0, 100) / 100f

    /**
     * Lays the segments out across [widthDp] for a person reading at [textScale].
     *
     * The gap and the floor both grow with the text scale, so a low-vision reader gets a strip whose bands
     * are still countable rather than a strip that shrank while the words around it grew. When the width
     * cannot hold floor-plus-gaps for every band, the gaps collapse first and the bands divide what is
     * left by their shares: the proportions survive, the air between them does not.
     */
    fun place(bands: List<EmblemBand>, widthDp: Float, textScale: Float = 1f): List<EmblemSlice> {
        if (bands.isEmpty() || widthDp <= 0f) return emptyList()
        val scale = textScale.coerceIn(1f, MAX_SCALE)
        val parts = shares(bands)
        val floor = MIN_SLICE_DP * scale
        var gap = BASE_GAP_DP * scale
        var room = widthDp - gap * (bands.size - 1)
        if (room < floor * bands.size) {
            gap = 0f
            room = widthDp
        }
        val slices = ArrayList<EmblemSlice>(bands.size)
        var cursor = 0f
        bands.forEachIndexed { index, band ->
            val width = max(0f, room * parts[index])
            slices += EmblemSlice(
                band = band,
                startX = cursor,
                width = width,
                fillWidth = width * fillOf(band),
                gap = gap,
            )
            cursor += width + gap
        }
        return slices
    }

    /** The strip's height for a given text scale, so the drawn bars and their floor agree. */
    fun heightForDp(textScale: Float = 1f): Float = BASE_HEIGHT_DP * textScale.coerceIn(1f, MAX_SCALE)

    /**
     * The one sentence the whole graphic is worth.
     *
     * TalkBack would otherwise read seven rectangles — and seven rectangles carrying no numbers of their
     * own is worse than nothing, because the person listening has to add them up. This says the total,
     * the completeness the caller already put into words, and by name the bands that are quiet, so an
     * absence is announced as an absence rather than inferred from a gap nobody described.
     */
    fun spokenDescription(percent: Int, caption: String?, quietLabels: List<String>): String =
        buildString {
            append("Итог $percent%.")
            if (!caption.isNullOrBlank()) append(" $caption.")
            if (quietLabels.isNotEmpty()) {
                val word = if (quietLabels.size == 1) "полоса" else "полосы"
                append(" Без сравнения $word: ${quietLabels.joinToString(", ")} — они показаны пустыми.")
            }
        }
}

/**
 * The emblem itself: the number, the strip that shows what the number rests on, and the completeness line
 * under it — one graphic that TalkBack reads as one statement.
 *
 * [caption] and [spoken] arrive already built by the caller, so the wording stays out of Compose and
 * testable; this composable draws what it is handed and nothing else.
 */
@Composable
fun ScoreEmblem(
    percent: Int,
    bands: List<EmblemBand>,
    caption: String?,
    spoken: String,
    modifier: Modifier = Modifier,
    digitsOn: Color = cardPaintedSurface(),
) {
    val track = MaterialTheme.colorScheme.surfaceVariant
    val quiet = MaterialTheme.colorScheme.outlineVariant
    val fontScale = LocalDensity.current.fontScale
    var visible by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { visible = true }
    val reveal by animateFloatAsState(
        targetValue = if (visible) 1f else 0f,
        animationSpec = tween(Motion.Slow),
        label = "emblemReveal",
    )
    Column(
        modifier = modifier
            .fillMaxWidth()
            // Digits, strip and caption are one claim; read separately they are a number, seven shapes
            // and a sentence, and the shapes carry no numbers of their own.
            .clearAndSetSemantics { contentDescription = spoken },
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.sm),
    ) {
        Text(
            text = "$percent%",
            style = MaterialTheme.typography.displaySmall.tabularDigits(),
            fontWeight = FontWeight.Bold,
            // The headline is 26sp Bold, which WCAG counts as large text, so 3:1 is the bar here —
            // the same rule the verdict line on this screen already reads from.
            color = scoreTextColor(percent, digitsOn, need = 3.0),
        )
        Canvas(
            modifier = Modifier
                .fillMaxWidth()
                .height(ScoreEmblemGeometry.heightForDp(fontScale).dp),
        ) {
            val slices = ScoreEmblemGeometry.place(bands, size.width / density, fontScale)
            slices.forEach { slice ->
                val x = slice.startX * density
                val width = slice.width * density
                if (slice.band.measured) {
                    drawRect(
                        color = track,
                        topLeft = Offset(x, 0f),
                        size = Size(width, size.height),
                    )
                    drawRect(
                        color = scoreColor(slice.band.score),
                        topLeft = Offset(x, 0f),
                        size = Size(slice.fillWidth * density * reveal, size.height),
                    )
                } else {
                    drawQuietSegment(x, width, size.height, quiet)
                }
            }
        }
        if (!caption.isNullOrBlank()) {
            Text(
                text = caption,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * A band nobody compared, drawn as a hole rather than as a low score: outlined, hatched, and in the
 * quietest tone the scheme owns. Filled with the track colour it would read as `0 %`, which the engine
 * never said — and painting its neutral half would be worse still, because that half is the absence of a
 * measurement rather than a measurement of the middle.
 */
private fun DrawScope.drawQuietSegment(
    x: Float,
    width: Float,
    height: Float,
    color: Color,
) {
    if (width <= 0f) return
    val border = 1.dp.toPx()
    drawRect(
        color = color,
        topLeft = Offset(x + border / 2f, border / 2f),
        size = Size(max(0f, width - border), max(0f, height - border)),
        style = Stroke(width = border),
    )
    // The hatch is clipped to the segment, so seven shapes stay seven shapes and the quiet part of one
    // band never walks into its neighbour.
    clipRect(left = x, top = 0f, right = x + width, bottom = height) {
        val step = 6.dp.toPx()
        var cursor = x - height
        while (cursor < x + width) {
            drawLine(
                color = color,
                start = Offset(cursor, height),
                end = Offset(cursor + height, 0f),
                strokeWidth = border,
            )
            cursor += step
        }
    }
}
