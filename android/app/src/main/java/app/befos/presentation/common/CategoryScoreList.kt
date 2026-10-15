package app.befos.presentation.common

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
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

internal fun categoryReadout(hasData: Boolean, score: Int): String =
    if (hasData) "$score%" else "нет данных"

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
 */
@Composable
fun CategoryScoreRow(score: CategoryScore, modifier: Modifier = Modifier, delayMs: Int = 0) {
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
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = Spacing.sm),
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
                text = if (score.weight > 0f) {
                    "${score.label.uppercase()} · важность ${Math.round(score.weight * 100)}%"
                } else {
                    score.label.uppercase()
                },
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
}

@Composable
fun CategoryScoreList(scores: List<CategoryScore>, modifier: Modifier = Modifier) {
    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
        scores.forEachIndexed { i, score ->
            CategoryScoreRow(score, delayMs = i * 60)
        }
    }
}
