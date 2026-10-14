package app.befos.presentation.compatibility

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.CompatibilityScore
import app.befos.core.designsystem.CompatibilitySkeleton
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.IrisSoft
import app.befos.core.designsystem.Mint
import app.befos.core.designsystem.compatibilityVerdict
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.WarningAmber
import app.befos.core.designsystem.answersWord
import app.befos.core.designsystem.scoreTextColor
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Explanation
import app.befos.presentation.common.CategoryScoreList

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CompatibilityScreen(
    matchId: String,
    onBack: () -> Unit,
    onOpenUniverse: () -> Unit,
    onOpenSection: (String) -> Unit,
    onEditProfile: () -> Unit,
) {
    val vm: CompatibilityViewModel =
        beFosViewModel { CompatibilityViewModel(it.matchRepository, it.testRepository, matchId) }
    val state by vm.uiState.collectAsState()

    Scaffold(
        topBar = { AppTopBar(title = "Совместимость", onBack = onBack) },
    ) { padding ->
        when {
            state.loading -> CompatibilitySkeleton(Modifier.padding(padding))
            state.data == null -> ErrorState(
                message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
                title = "Не удалось рассчитать",
                onRetry = vm::load,
                modifier = Modifier.padding(padding),
            )
            else -> {
                val data = state.data!!
                Column(
                    modifier = Modifier
                        .padding(padding)
                        .fillMaxSize()
                        .background(MaterialTheme.colorScheme.background)
                        .verticalScroll(rememberScrollState())
                        .padding(horizontal = Spacing.gutter, vertical = Spacing.xl),
                    verticalArrangement = Arrangement.spacedBy(Spacing.section),
                ) {
                    // Hero panel: iris-tinted, ring + verdict.
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(MaterialTheme.shapes.large)
                            .background(Brush.verticalGradient(listOf(IrisSoft, MaterialTheme.colorScheme.surface))),
                    ) {
                        Column(
                            modifier = Modifier.padding(Spacing.xxl),
                            horizontalAlignment = Alignment.CenterHorizontally,
                            verticalArrangement = Arrangement.spacedBy(Spacing.md),
                        ) {
                            Text(
                                text = "ВАША СОВМЕСТИМОСТЬ",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            CompatibilityScore(
                                percent = data.overall,
                                size = 160.dp,
                                strokeWidth = 12.dp,
                                // The panel below is washed from IrisSoft to the surface, so
                                // the digits are read against the darker stop, not against
                                // the white of `surface`.
                                digitsOn = IrisSoft,
                            )
                            Text(
                                compatibilityVerdict(data.overall),
                                style = MaterialTheme.typography.headlineMedium,
                                fontWeight = FontWeight.Bold,
                                // headlineMedium is 21sp, and Bold at 21sp clears WCAG's
                                // 18.66sp-Bold bar for large text, so the bar here is 3:1
                                // rather than 4.5:1. The wash decides the background: on the
                                // flat white the raw ScoreMid stop measures 3.45:1 and looks
                                // legal, on the IrisSoft end the same pixels measure 2.87:1 —
                                // which is why the dark stop is the one asked about.
                                color = scoreTextColor(data.overall, IrisSoft, need = 3.0),
                            )
                            Text(
                                "Совпадения считаны по анкетам и тесту — это не психологический диагноз.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }

                    AppButton(
                        text = "Открыть карту пары",
                        onClick = onOpenUniverse,
                        secondary = true,
                        modifier = Modifier.fillMaxWidth(),
                    )

                    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                        SectionHeader("По категориям")
                        AppCard(modifier = Modifier.fillMaxWidth()) {
                            Column(
                                modifier = Modifier.padding(Spacing.xl),
                                verticalArrangement = Arrangement.spacedBy(Spacing.lg),
                            ) {
                                CategoryScoreList(data.categories)
                                Text(
                                    "Итог — сумма категорий, каждая со своим весом: сильнее влияет то, " +
                                        "что важнее для знакомства. Категория, где сравнивать было нечего, " +
                                        "помечена «нет данных» и осталась пустой.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                // …and a person who wants that band filled has to learn from the real
                                // counts what fills it, instead of guessing between the questionnaire
                                // and the profile fields.
                                state.sections?.let { sections ->
                                    data.categories.filterNot { it.hasData }.forEach { band ->
                                        BandGapRow(
                                            band = band,
                                            gap = bandGap(band, sections.firstOrNull { it.key == band.category }),
                                            onOpenSection = onOpenSection,
                                            onEditProfile = onEditProfile,
                                        )
                                    }
                                }
                            }
                        }
                    }

                    if (data.strengths.isNotEmpty()) {
                        Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                            SectionHeader("Почему вы подходите")
                            ExplanationBlock(items = data.strengths, accent = Mint)
                        }
                    }
                    if (data.differences.isNotEmpty()) {
                        Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                            SectionHeader("Что может отличаться")
                            ExplanationBlock(items = data.differences, accent = WarningAmber)
                        }
                    }
                    if (data.sharedInterests.isNotEmpty()) {
                        Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                            SectionHeader("Общие интересы")
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(Spacing.sm), verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                                data.sharedInterests.forEach { slug ->
                                    InterestChip(label = prettifySlug(slug))
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

/** Data-derived explanation block: accent dot per real reason. */
@Composable
private fun ExplanationBlock(items: List<Explanation>, accent: Color) {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            items.forEach { item ->
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.md),
                    verticalAlignment = Alignment.Top,
                ) {
                    Box(
                        modifier = Modifier
                            .padding(top = 6.dp)
                            .size(10.dp)
                            .clip(CircleShape)
                            .background(accent),
                    )
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(item.label, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Text(
                            item.text,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
}

internal fun prettifySlug(slug: String): String =
    slug.replace('_', ' ').replace('-', ' ').replaceFirstChar { it.uppercase() }

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
 */
internal fun bandGap(band: CategoryScore, section: CategoryProgress?): BandGap = when {
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
            "по категории «${band.label}», и с ответами партнёра они не пересеклись. $NEUTRAL",
        cta = "Продолжить раздел",
        target = GapTarget.SECTION,
    )
    else -> BandGap(
        line = "Раздел «${band.label}» закрыт с вашей стороны: ${section.total} из ${section.total}. " +
            "Значит, в нём нет ответов партнёра. $NEUTRAL",
        cta = "",
        target = GapTarget.NONE,
    )
}

/** One empty band, what fills it, and the way there — only when the data names one. */
@Composable
private fun BandGapRow(
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
