package app.befos.presentation.pair

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Insights
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
import androidx.compose.ui.text.font.FontWeight
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.IrisSoft
import app.befos.core.designsystem.ProfileSkeleton
import app.befos.core.designsystem.ScoreEmblem
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.cardPaintedSurface
import app.befos.core.designsystem.compatibilityVerdict
import app.befos.core.designsystem.scoreTextColor
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.PairProfile
import app.befos.presentation.compatibility.completenessCaption
import app.befos.presentation.compatibility.emblemBands
import app.befos.presentation.compatibility.emblemSpoken
import app.befos.presentation.compatibility.prettifySlug

/**
 * The pair's own reading of itself: the two people, the number with what it rests on, the interests they
 * share, and the hour they are standing on.
 *
 * This is a surface for reading, not a second editor. Everything here is reachable from a screen that
 * already presents it well — the pair's plans, their conversation, the detailed analysis — so the layout
 * repeats no control from those places: no hour to move, no word to write, no filter to set. What it adds
 * is one page where a pair can see the whole of themselves at once, and the doors down to each part.
 *
 * The state lives in [PairProfileViewModel], so a rotation cannot put the person back at a skeleton.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun PairProfileScreen(
    matchId: String,
    onBack: () -> Unit,
    onOpenCompatibility: () -> Unit,
    // The pair's plans, brought to the arrangement this page is naming when there is one.
    onOpenPlans: (String?) -> Unit,
) {
    val vm: PairProfileViewModel =
        beFosViewModel { PairProfileViewModel(it.matchRepository, matchId) }
    val state by vm.uiState.collectAsState()

    Scaffold(
        topBar = { AppTopBar(title = "Профиль пары", onBack = onBack) },
    ) { padding ->
        when {
            state.loading -> ProfileSkeleton(Modifier.padding(padding))
            state.data == null && state.gone ->
                // The pair is gone, so the read cannot be retried into succeeding: the page says what
                // happened and gives the way back, which is the only honest control left on it.
                EmptyState(
                    title = "Профиля пары больше нет",
                    message = state.error ?: "Эта пара распалась, и читать здесь нечего.",
                    modifier = Modifier.padding(padding),
                    overline = "Пара",
                )
            state.data == null -> ErrorState(
                title = "Не удалось прочесть пару",
                message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
                onRetry = vm::load,
                modifier = Modifier.padding(padding),
            )
            else -> PairProfileContent(
                profile = state.data!!,
                modifier = Modifier.padding(padding),
                onOpenCompatibility = onOpenCompatibility,
                onOpenPlans = onOpenPlans,
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun PairProfileContent(
    profile: PairProfile,
    modifier: Modifier,
    onOpenCompatibility: () -> Unit,
    onOpenPlans: (String?) -> Unit,
) {
    val compatibility = profile.compatibility
    Column(
        modifier = modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Spacing.gutter, vertical = Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.section),
    ) {
        // Who they are and since when — the only part of this page that is about the pair rather than
        // about the engine. The order is the document's own, identical for both halves.
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .clip(MaterialTheme.shapes.large)
                .background(Brush.verticalGradient(listOf(IrisSoft, MaterialTheme.colorScheme.surface))),
        ) {
            Column(
                modifier = Modifier.padding(Spacing.xxl),
                verticalArrangement = Arrangement.spacedBy(Spacing.lg),
            ) {
                Text(
                    text = "ЭТА ПАРА",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                pairPeopleWord(profile.people)?.let {
                    Text(
                        it,
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold,
                    )
                }
                pairSinceDay(profile.since)?.let { day ->
                    Text(
                        "Пара с $day",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Text(
                    plansTotalWord(profile.plansTotal),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
            SectionHeader(
                title = "Насколько вы подходите",
                subtitle = "Та же цифра и те же полосы, что читает экран совместимости: пустые части — " +
                    "то, что сравнивать было не с чем.",
            )
            AppCard(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(Spacing.xl),
                    verticalArrangement = Arrangement.spacedBy(Spacing.md),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    ScoreEmblem(
                        percent = compatibility.overall,
                        bands = emblemBands(compatibility.categories),
                        caption = completenessCaption(compatibility.bandsMeasured, compatibility.bandsTotal),
                        spoken = emblemSpoken(compatibility),
                        // The digest sits on a card, and a card is painted with its tint: the digits have
                        // to be solved against those pixels rather than the flat `surface` the scheme
                        // names, because WCAG thresholds are floors.
                        digitsOn = cardPaintedSurface(),
                    )
                    Text(
                        compatibilityVerdict(compatibility.overall),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        // titleMedium is 16sp — ordinary text to WCAG, so this line asks for 4.5:1 rather
                        // than the 3:1 the larger headline on the compatibility page is allowed.
                        color = scoreTextColor(compatibility.overall, cardPaintedSurface()),
                    )
                    AppButton(
                        text = "Подробный разбор",
                        onClick = onOpenCompatibility,
                        secondary = true,
                        leadingIcon = Icons.Filled.Insights,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }

        Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
            SectionHeader("Ближайшая договорённость")
            AppCard(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(Spacing.xl),
                    verticalArrangement = Arrangement.spacedBy(Spacing.md),
                ) {
                    // The hour is quoted from the plan itself, in the same words the chat's plan card and
                    // the ideas card use. Nothing here can move it, so nothing here pretends to.
                    nextPlanWord(profile.plan)?.let { hour ->
                        Text(hour, style = MaterialTheme.typography.titleMedium)
                    } ?: Text(
                        noPlanWord(profile.plansTotal),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    AppButton(
                        text = if (profile.plan != null) "Открыть планы" else "Смотреть планы",
                        onClick = { onOpenPlans(profile.plan?.planId) },
                        variant = AppButtonVariant.Ghost,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }

        if (compatibility.sharedInterests.isNotEmpty()) {
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("Общее")
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    compatibility.sharedInterests.forEach { interest ->
                        InterestChip(label = prettifySlug(interest))
                    }
                }
            }
        }
    }
}
