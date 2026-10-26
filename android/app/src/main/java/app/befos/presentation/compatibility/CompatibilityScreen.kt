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
import app.befos.core.designsystem.CompatibilitySkeleton
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.IrisSoft
import app.befos.core.designsystem.Mint
import app.befos.core.designsystem.ScoreEmblem
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.WarningAmber
import app.befos.core.designsystem.compatibilityVerdict
import app.befos.core.designsystem.scoreTextColor
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Compatibility
import app.befos.domain.model.Explanation
import app.befos.presentation.common.BandGapRow
import app.befos.presentation.common.CategoryScoreList
import app.befos.presentation.common.bandGap
import app.befos.presentation.common.bandWeightWord
import app.befos.presentation.common.myProfileEntryWord
import app.befos.presentation.common.pairBandsCaption
import app.befos.presentation.universe.starterDraftFor

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun CompatibilityScreen(
    matchId: String,
    onBack: () -> Unit,
    onOpenUniverse: () -> Unit,
    onOpenSection: (String) -> Unit,
    onEditProfile: () -> Unit,
    onOpenMyProfile: () -> Unit,
    // Where the starter line leads: a drafted sentence, already in the pair's own words, goes to the
    // composer of the thread and waits there. Nothing is sent by this screen.
    onAskInChat: (String) -> Unit,
) {
    val vm: CompatibilityViewModel =
        beFosViewModel { CompatibilityViewModel(it.matchRepository, it.testRepository, matchId) }
    val state by vm.uiState.collectAsState()

    Scaffold(
        topBar = { AppTopBar(title = "Совместимость", onBack = onBack) },
    ) { padding ->
        when {
            state.loading -> CompatibilitySkeleton(Modifier.padding(padding))
            state.data == null && state.gone ->
                // The pair is gone rather than the read having failed: «Повторить» here asks the server
                // for a match it has already answered there is no such match, which is the dead control
                // this app removed from the chat and the pair pages for the same reason.
                EmptyState(
                    title = "Чтения больше нет",
                    message = state.error ?: "Эта пара распалась, и её совместимость негде прочитать.",
                    modifier = Modifier.padding(padding),
                    overline = "Пара",
                )
            state.data == null -> ErrorState(
                message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
                title = "Не удалось рассчитать",
                onRetry = vm::load,
                modifier = Modifier.padding(padding),
            )
            else -> CompatibilityContent(
                state = state,
                modifier = Modifier.padding(padding),
                onToggleBand = vm::toggleBand,
                onOpenUniverse = onOpenUniverse,
                onOpenSection = onOpenSection,
                onEditProfile = onEditProfile,
                onOpenMyProfile = onOpenMyProfile,
                onAskInChat = onAskInChat,
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun CompatibilityContent(
    state: CompatibilityUiState,
    modifier: Modifier,
    onToggleBand: (String) -> Unit,
    onOpenUniverse: () -> Unit,
    onOpenSection: (String) -> Unit,
    onEditProfile: () -> Unit,
    onOpenMyProfile: () -> Unit,
    onAskInChat: (String) -> Unit,
) {
    val data = state.data ?: return
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Spacing.gutter, vertical = Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.section),
    ) {
        // Hero: iris-tinted, with the number drawn as what it rests on rather than as an arc.
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
                ScoreEmblem(
                    percent = data.overall,
                    bands = emblemBands(data.categories),
                    caption = completenessCaption(data.bandsMeasured, data.bandsTotal),
                    spoken = emblemSpoken(data),
                    // The panel washes from IrisSoft to the surface, so the digits are read against the
                    // darker stop rather than against the white of `surface`.
                    digitsOn = IrisSoft,
                )
                Text(
                    compatibilityVerdict(data.overall),
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    // headlineMedium is 21sp, and Bold at 21sp clears WCAG's 18.66sp-Bold bar for large
                    // text, so the bar here is 3:1 rather than 4.5:1. The wash decides the background: on
                    // the flat white the raw ScoreMid stop measures 3.45:1 and looks legal, on the IrisSoft
                    // end the same pixels measure 2.87:1 — which is why the dark stop is the one asked about.
                    color = scoreTextColor(data.overall, IrisSoft, need = 3.0),
                )
                measuredWeightCaption(data.measuredWeight)?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Text(
                    "Совпадения считаны по анкетам и тесту — это не психологический диагноз.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                // Which engine wrote the number, because two versions can print the same percent from
                // different answers, and a pair comparing this reading with last spring's has to be able
                // to tell whether the two are the same calculation at all.
                Text(
                    "версия расчёта ${data.engineVersion}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        if (data.starter.isNotBlank()) {
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("С чего начать")
                AppCard(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.padding(Spacing.xl),
                        verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                    ) {
                        Text(data.starter, style = MaterialTheme.typography.bodyLarge)
                        // The door opens only over a place the engine itself named. A starter that points
                        // at the questionnaire rather than at something the pair can say would put the
                        // app's own instruction into somebody's thread, and a drafted sentence nobody
                        // could have typed is the worse of the two silences.
                        starterDraftFor(data.starter)?.let { draft ->
                            TextButton(onClick = { onAskInChat(draft) }) {
                                Text("Начать в чате")
                            }
                        }
                    }
                }
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
                    CategoryScoreList(
                        scores = data.categories,
                        expandedCategory = state.expandedBand,
                        onToggle = { band -> onToggleBand(band.category) },
                        detail = { band ->
                            BandDetail(
                                band = band,
                                data = data,
                                state = state,
                                onOpenSection = onOpenSection,
                                onEditProfile = onEditProfile,
                            )
                        },
                    )
                    quietBandsHint(data.categories)?.let {
                        Text(
                            it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Text(
                        pairBandsCaption(),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    // The caption above says these percents are not one person's trait.
                    // Saying it without a way to the reading that is would leave the person
                    // with a claim and no place to check it — the same screen the profile
                    // tab and the questionnaire result open, under the same word.
                    TextButton(
                        onClick = onOpenMyProfile,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(myProfileEntryWord())
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
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    data.sharedInterests.forEach { slug ->
                        InterestChip(label = prettifySlug(slug))
                    }
                }
            }
        }
    }
}

/**
 * What one band measures, how heavy it is, whether it was measured at all, and what its number means.
 *
 * The panel is built out of the answer and nothing else. An unmeasured band is told as an unmeasured band
 * — the row already left its bar empty, and the panel says which of the person's own answers would fill
 * it, when the counts are on the device to say so. The meaning of a measured band comes from the lines the
 * engine wrote about that very band, quoted rather than retold; where it wrote none, the panel says that
 * too instead of dressing the percent up in the screen's own words.
 */
@Composable
private fun BandDetail(
    band: CategoryScore,
    data: Compatibility,
    state: CompatibilityUiState,
    onOpenSection: (String) -> Unit,
    onEditProfile: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        Text(
            bandMeasuredWord(band),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
        )
        bandWeightWord(band.weight)?.let {
            Text(
                // The word the rows print, said once more where it can finally be explained: how much of
                // the total this band moved, not how good the pair is at it.
                text = "$it — столько полоса добавила в итог",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        val meaning = bandMeaning(band, data.strengths + data.differences)
        if (meaning.isEmpty()) {
            Text(
                bandMeaningAbsenceWord(band),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            meaning.forEach { line ->
                Text(line, style = MaterialTheme.typography.bodyMedium)
            }
        }
        if (!band.hasData) {
            // What would fill the hole, from the counts this screen read for exactly this question — and
            // nothing at all when the counts never arrived, because a door the device cannot name is worse
            // than no door.
            state.sections?.let { sections ->
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

/**
 * The engine's own lines, each under the kind of difference it names.
 *
 * A difference between two answers is not an error in either of them, and the screen used to print the
 * two lists with nothing but an accent colour between them — so `discussion` and `complementarity` read
 * as the same bad news. The kind now arrives from the backend, and the hint under it is the shortest
 * sentence that says what was compared rather than what to make of it.
 */
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
                        Text(
                            kindLine(item),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            item.text,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        explanationKindHint(item.connection).takeIf {
                            explanationKindWord(item.connection) != null
                        }?.let { hint ->
                            Text(
                                hint,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}

/** Label plus the kind the engine named, or the label alone when the answer named no kind. */
internal fun kindLine(item: Explanation): String =
    explanationKindWord(item.connection)?.let { "${item.label} · $it" } ?: item.label

/**
 * The line that keeps an unmeasured band findable when its explanation has moved into the panel a person
 * has to open.
 *
 * null when every band was compared: a hint about holes that are not there would tell the reader the
 * screen has something to apologise for.
 */
internal fun quietBandsHint(categories: List<CategoryScore>): String? {
    val quiet = categories.count { !it.hasData }
    if (quiet == 0) return null
    val word = if (quiet == 1) "полоса" else "полосы"
    return "Полос без сравнения: $quiet — они показаны пустыми. Нажмите на такую $word, чтобы увидеть, чем она заполняется."
}

internal fun prettifySlug(slug: String): String =
    slug.replace('_', ' ').replace('-', ' ').replaceFirstChar { it.uppercase() }
