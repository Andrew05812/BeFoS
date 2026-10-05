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
import app.befos.core.designsystem.scoreTextColor
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.Explanation
import app.befos.presentation.common.CategoryScoreList

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CompatibilityScreen(matchId: String, onBack: () -> Unit) {
    val vm: CompatibilityViewModel = beFosViewModel { CompatibilityViewModel(it.matchRepository, matchId) }
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

                    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                        SectionHeader("По категориям")
                        AppCard(modifier = Modifier.fillMaxWidth()) {
                            Column(
                                modifier = Modifier.padding(Spacing.xl),
                                verticalArrangement = Arrangement.spacedBy(Spacing.lg),
                            ) {
                                CategoryScoreList(data.categories)
                                Text(
                                    "Итог — среднее по категориям: то, что важнее для знакомства, влияет сильнее.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
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
