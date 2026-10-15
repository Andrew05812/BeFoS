package app.befos.presentation.common

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.answersWord
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore

/** Where the person is sent to fill an empty band: their own section of the test, or the profile. */
internal enum class GapTarget { SECTION, PROFILE, NONE }

internal data class BandGap(val line: String, val cta: String, val target: GapTarget)

private const val NEUTRAL = "Полоса держится на нейтральных 50% — это не оценка, а отсутствие сравнения."

/**
 * What fills a band the engine left without data, said from the two facts the screen has: the
 * counts of the person's own section, and which keys the questionnaire asks about at all.
 *
 * The empty band means the shared trait set came out empty, so the line names whose side is short
 * only when the numbers can prove it. A closed section is the one case they do: the person holds
 * every trait of that section, so nothing of the partner's can fail to match it, and the missing
 * answers are on the other side. Where the counts cannot tell, the screen says only that there was
 * nothing to compare — and offers no action it cannot justify.
 *
 * Written once because two screens read the same band: the pair page, and the card of a person the
 * reader has not matched with yet. Both take their percents from the same two questionnaires, so a
 * second copy of these sentences would be a second opinion about one gap.
 *
 * `peer` is the one thing the two screens cannot share: the second questionnaire belongs to a
 * partner on the pair page and to a stranger on a card, and calling a stranger «партнёр» would
 * claim a pair that does not exist. It arrives in the genitive because both sentences that use it
 * put it after a noun.
 */
internal fun bandGap(
    band: CategoryScore,
    section: CategoryProgress?,
    peer: String = "партнёра",
): BandGap = when {
    section == null && band.category == "interests" -> BandGap(
        line = "Интересы приходят из профиля: назвал их не каждый из вас, и сравнивать наборы не с чем. $NEUTRAL",
        cta = "Заполнить профиль",
        target = GapTarget.PROFILE,
    )
    section == null && band.category == "goals" -> BandGap(
        line = "Цель знакомства тоже берётся из профиля: без неё у одного из вас измерять нечего. $NEUTRAL",
        cta = "Заполнить профиль",
        target = GapTarget.PROFILE,
    )
    section == null -> BandGap(
        line = "В категории «${band.label}» сравнивать было нечего. $NEUTRAL",
        cta = "",
        target = GapTarget.NONE,
    )
    section.answered == 0 -> BandGap(
        line = "Раздел «${band.label}» вы не начинали: в нём ${section.total} ${answersWord(section.total)}. " +
            "Без ваших ответов сравнивать нечего. $NEUTRAL",
        cta = "Пройти раздел",
        target = GapTarget.SECTION,
    )
    section.answered < section.total -> BandGap(
        line = "У вас ${section.answered} ${answersWord(section.answered)} из ${section.total} " +
            "по категории «${band.label}», и с ответами $peer они не пересеклись. $NEUTRAL",
        cta = "Продолжить раздел",
        target = GapTarget.SECTION,
    )
    else -> BandGap(
        line = "Раздел «${band.label}» закрыт с вашей стороны: ${section.total} из ${section.total}. " +
            "Значит, в нём нет ответов $peer. $NEUTRAL",
        cta = "",
        target = GapTarget.NONE,
    )
}

/** One empty band, what fills it, and the way there — only when the data names one. */
@Composable
internal fun BandGapRow(
    band: CategoryScore,
    gap: BandGap,
    onOpenSection: (String) -> Unit,
    onEditProfile: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.medium)
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f))
            .padding(start = Spacing.lg, end = Spacing.lg, top = Spacing.md, bottom = Spacing.xs),
        verticalArrangement = Arrangement.spacedBy(Spacing.xs),
    ) {
        Text(
            band.label.uppercase(),
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            gap.line,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface,
        )
        when (gap.target) {
            GapTarget.SECTION -> TextButton(onClick = { onOpenSection(band.category) }) {
                Text(gap.cta, fontWeight = FontWeight.SemiBold)
            }
            GapTarget.PROFILE -> TextButton(onClick = onEditProfile) {
                Text(gap.cta, fontWeight = FontWeight.SemiBold)
            }
            GapTarget.NONE -> Unit
        }
    }
}
