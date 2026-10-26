package app.befos.presentation.common

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.semantics.ProgressBarRangeInfo
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.progressBarRangeInfo
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.ScoreLow
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.cardPaintedSurface
import app.befos.core.designsystem.scoreColor
import app.befos.core.designsystem.scoreTextColor
import app.befos.core.designsystem.tabularDigits
import app.befos.domain.model.CategoryScore
import kotlin.math.roundToInt

internal fun categoryReadout(hasData: Boolean, score: Int): String =
    if (hasData) "$score%" else "нет данных"

/**
 * The weight as its row prints it, or null when the answer carries none — the personal test profile has
 * none, and «важность 0%» over a band that was never weighted would be a lie about the engine.
 *
 * Written once because the row's own label and the sentence a screen reader gets are the same claim: two
 * spellings of one weight is how a person starts wondering which number the band actually has.
 */
internal fun bandWeightWord(weight: Double): String? = when {
    !weight.isFinite() || weight <= 0.0 -> null
    else -> "важность ${(weight * 100).roundToInt()}%"
}

/**
 * The whole band in one spoken sentence.
 *
 * Without it TalkBack read this row as two or three separate fragments — a label, a bare number, a bar
 * — and a person listening had to work out which percent belonged to which band and whether an empty bar
 * was a low score or no score. The label, the reading and the weight are named together, and the
 * sentence says out loud what the drawing already shows: that a band nobody compared was not compared.
 */
internal fun categorySpoken(
    score: CategoryScore,
    expandable: Boolean,
    expanded: Boolean = false,
): String {
    val weight = bandWeightWord(score.weight)?.let { ", $it" }.orEmpty()
    val reading = if (score.hasData) {
        "сходство ${score.score}%"
    } else {
        "${categoryReadout(hasData = false, score = score.score)}, полоса не сверялась"
    }
    val door = when {
        !expandable -> ""
        expanded -> " Развернуто. Нажмите, чтобы свернуть."
        else -> " Нажмите, чтобы узнать, что в этой полосе измеряется."
    }
    return "${score.label}: $reading$weight.$door"
}

/**
 * What the percents of a pair's list measure — the sentence every screen that draws [CategoryScoreList]
 * prints under it.
 *
 * The list is shared, and so is the reading its numbers invite. On the pair screen a percent can only
 * be read as a similarity, because both people are on screen. On another person's profile the same
 * digits sit under her name, and «важность 80%» in the row above them is the engine's contribution
 * weight, not a trait of the person in the photo — so that screen has to say the number is built from
 * the reader's answers as much as from hers. Written once because two wordings for one list drift the
 * moment either screen is edited, and it carries no digit of its own: a caption with a percent in it
 * competes with the percents it stands under.
 */
internal fun pairBandsCaption(): String =
    "Эти проценты — сходство двух анкет, а не черта одного человека: для другой пары то же число " +
        "будет другим. Слово «важность» над полосой — сколько категория добавила в итог. " +
        "Итог — сумма категорий, каждая со своим весом: сильнее влияет то, что важнее для " +
        "знакомства, а категория, где сравнивать было нечего, помечена «нет данных» и осталась пустой."

/**
 * Compatibility category breakdown: animated gradient bars that fill on
 * appear — the signature visualization of the engine output.
 *
 * The row is one statement to a screen reader ([categorySpoken]) and one claim to the eye: a band the
 * engine never compared gets an empty track, its own word, and no fill of any colour. When the caller
 * hands it [onToggle] and a [detail] slot the row also opens — the pair's screen uses that to say what the
 * band measures, how heavy it is and what its number means, and screens that only list the bands (the
 * person's own profile, the card of somebody they have not matched with) keep the row exactly as it was.
 */
@Composable
fun CategoryScoreRow(
    score: CategoryScore,
    modifier: Modifier = Modifier,
    delayMs: Int = 0,
    expanded: Boolean = false,
    onToggle: (() -> Unit)? = null,
    detail: (@Composable () -> Unit)? = null,
) {
    var visible by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { visible = true }
    // A band nobody answered holds the engine's neutral half, and a bar filling to that half
    // reads as a middling measurement. It gets an empty track and its own word instead.
    val fraction by animateFloatAsState(
        targetValue = if (visible && score.hasData) score.score / 100f else 0f,
        animationSpec = tween(durationMillis = Motion.Slow, delayMillis = delayMs, easing = androidx.compose.animation.core.FastOutSlowInEasing),
        label = "categoryBar",
    )
    val color = scoreColor(score.score)
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(Spacing.xs),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = Spacing.sm)
                .then(if (onToggle != null) Modifier.clickable(onClick = onToggle) else Modifier)
                // The bar and its two numbers are one fact about one band, and the progress range is the
                // same fact in the channel a screen reader announces as a value rather than as a picture.
                .clearAndSetSemantics {
                    contentDescription = categorySpoken(
                        score,
                        expandable = onToggle != null,
                        expanded = expanded,
                    )
                    progressBarRangeInfo = ProgressBarRangeInfo(
                        if (score.hasData) score.score / 100f else 0f,
                        0f..1f,
                    )
                },
            verticalArrangement = Arrangement.spacedBy(Spacing.xs),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    // Weight only exists in the pair-compatibility calculation; the
                    // personal test profile has none, so "важность 0%" would be a lie.
                    // "Вес" is engine vocabulary — the user reads how much a category mattered.
                    text = bandWeightWord(score.weight)?.let {
                        "${score.label.uppercase()} · $it"
                    } ?: score.label.uppercase(),
                    style = MaterialTheme.typography.labelSmall.tabularDigits(),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    text = categoryReadout(score.hasData, score.score),
                    style = MaterialTheme.typography.titleMedium.tabularDigits(),
                    fontWeight = FontWeight.Bold,
                    // 16sp bold is not "large text" to WCAG, and the raw score hue is a fill
                    // color: ScoreLow reads 2.33:1 on a card, so a low category — the one a
                    // user most needs to read — was the least legible number on the screen.
                    // A band with no measurement has no score hue to lose, so it takes the
                    // ordinary body colour and its colour carries no claim.
                    color = if (score.hasData) {
                        scoreTextColor(score.score, cardPaintedSurface())
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
            }
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(10.dp)
                    .clip(RoundedCornerShape(5.dp))
                    .background(
                        if (score.hasData) {
                            MaterialTheme.colorScheme.surfaceVariant
                        } else {
                            MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f)
                        }
                    ),
            ) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth(fraction)
                        .height(10.dp)
                        .clip(RoundedCornerShape(5.dp))
                        .background(Brush.horizontalGradient(listOf(ScoreLow, color))),
                )
            }
        }
        if (onToggle != null && detail != null) {
            AnimatedVisibility(visible = expanded) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(MaterialTheme.shapes.medium)
                        .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f))
                        .padding(Spacing.lg),
                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    detail()
                }
            }
        }
    }
}

@Composable
fun CategoryScoreList(
    scores: List<CategoryScore>,
    modifier: Modifier = Modifier,
    expandedCategory: String? = null,
    onToggle: ((CategoryScore) -> Unit)? = null,
    detail: (@Composable (CategoryScore) -> Unit)? = null,
) {
    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
        scores.forEachIndexed { i, score ->
            CategoryScoreRow(
                score = score,
                delayMs = i * 60,
                expanded = expandedCategory == score.category,
                onToggle = onToggle?.let { toggle -> { toggle(score) } },
                detail = detail?.let { slot -> { slot(score) } },
            )
        }
    }
}
