package app.befos.presentation.profile

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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.EmberGradient
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.ProfileSkeleton
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.answersWord
import app.befos.core.designsystem.tabularDigits
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.CategoryProgress
import app.befos.presentation.common.CategoryScoreRow
import app.befos.presentation.test.BandAxes
import app.befos.presentation.test.bandsWithAxes
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * The person's own compatibility profile, openable at any time.
 *
 * The questionnaire used to be readable once: the evening it was scored. This screen is the reading
 * that comes later — the same bands and the same positions under them, now read back from the
 * server instead of handed over by the scoring — plus the two things the results card cannot say:
 * how much of the questionnaire is filled, and when the profile last changed.
 */
@Composable
fun MyProfileScreen(
    onBack: () -> Unit,
    onOpenTest: (String?) -> Unit,
) {
    val vm: MyProfileViewModel = beFosViewModel { MyProfileViewModel(it.testRepository) }
    val state by vm.uiState.collectAsState()

    LifecycleResumeEffect(Unit) {
        // Coming back from the questionnaire has to show the profile the new answers produced:
        // the numbers on this screen are the engine's, and the engine rescored them while the
        // person was away.
        vm.refreshSilently()
        onPauseOrDispose { }
    }

    Scaffold(
        topBar = { AppTopBar(title = "Мой профиль совместимости", onBack = onBack) },
    ) { padding ->
        val profile = state.profile
        when {
            state.loading -> ProfileSkeleton(Modifier.padding(padding))
            state.error != null && profile == null -> ErrorState(
                message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
                title = "Профиль не загрузился",
                onRetry = vm::load,
                modifier = Modifier.padding(padding),
            )
            // Nothing has ever been scored. This is the whole screen, not a block inside a
            // scroll: a profile with no bands has no content to scroll past, and the one thing
            // the person needs here is the way into the questionnaire.
            profile != null && profile.categories.isEmpty() -> EmptyState(
                title = "Профиля ещё нет",
                message = "Ни одна полоса не посчитана: алгоритм собирает профиль из ответов анкеты, " +
                    "а ваших ответов у него пока нет. Это не нули в полосах, а отсутствие " +
                    "измерения — проценты появятся, когда анкета будет закрыта.",
                overline = "Профиль",
                actionLabel = "Пройти анкету",
                onAction = { onOpenTest(null) },
                modifier = Modifier.padding(padding),
            )
            else -> MyProfileContent(state, onOpenTest, vm::refreshSilently)
        }
    }
}

@Composable
private fun MyProfileContent(
    state: MyProfileUiState,
    onOpenTest: (String?) -> Unit,
    onRetry: () -> Unit,
) {
    val profile = state.profile ?: return
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .padding(
                horizontal = Spacing.gutter,
                vertical = Spacing.xl,
            ),
        verticalArrangement = Arrangement.spacedBy(Spacing.xxl),
    ) {
        state.refreshError?.let {
            InlineNotice(it, actionLabel = "Повторить", onAction = onRetry)
        }

        Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            Text(
                "МОЙ ПРОФИЛЬ СОВМЕСТИМОСТИ",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                "Так алгоритм читает ваши ответы",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                measuredWord(profile.axes.size),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            updatedAtWord(profile.updatedAt)?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        // The five percents are what the compatibility of a pair is built from, so a screen that
        // showed them alone would be a summary of a reading nobody can check. Each band keeps the
        // order the route sent it in, and its positions open underneath it in the same words and
        // the same percent the universe map of a pair prints.
        Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
            SectionHeader("Полосы профиля", subtitle = axisGlossHint())
            AppCard(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(Spacing.xl)) {
                    bandsWithAxes(profile).forEachIndexed { i, (band, axes) ->
                        CategoryScoreRow(band, delayMs = i * 60)
                        if (axes.isNotEmpty()) BandAxes(axes)
                    }
                }
            }
        }

        CoverageCard(
            percent = state.progress?.percent,
            failed = state.progress == null && state.progressFailed,
            answered = state.answered,
            total = state.total,
            openSections = state.openSections,
            onOpenSection = onOpenTest,
        )

        AppButton(
            text = if (state.openSections.isEmpty()) "Пройти анкету заново" else "Продолжить анкету",
            onClick = { onOpenTest(null) },
            variant = AppButtonVariant.Tonal,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

/** How full the questionnaire is, and which of its sections would move the profile furthest. */
@Composable
private fun CoverageCard(
    percent: Int?,
    failed: Boolean,
    answered: Int,
    total: Int,
    openSections: List<CategoryProgress>,
    onOpenSection: (String?) -> Unit,
) {
    var visible by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { visible = true }
    val fill by animateFloatAsState(
        targetValue = if (visible && !failed) (percent ?: 0) / 100f else 0f,
        animationSpec = tween(Motion.Slow, easing = androidx.compose.animation.core.FastOutSlowInEasing),
        label = "coverageFill",
    )
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                    Text(
                        "ЗАПОЛНЕНИЕ АНКЕТЫ",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        coverageWord(answered, total, failed),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        if (failed) "—" else "${percent ?: 0}%",
                        style = MaterialTheme.typography.headlineSmall.tabularDigits(),
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        "отвечено",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(10.dp)
                    .clip(RoundedCornerShape(5.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Box(
                    Modifier
                        .fillMaxWidth(fill)
                        .height(10.dp)
                        .clip(RoundedCornerShape(5.dp))
                        .background(EmberGradient),
                )
            }
            // A section with nothing answered is the one that moves the profile most: its band is
            // either missing or averaged over fewer positions than the others. Said as counts the
            // server gave, with a way into the section — not as a promise about the percent.
            openSections.forEach { section ->
                Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                    Text(
                        sectionGapWord(section),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    TextButton(onClick = { onOpenSection(section.key) }) {
                        Text(gapCtaWord(section), fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }
    }
}

/**
 * How many answers the questionnaire holds, in the counts the progress route returned.
 *
 * The failed case is named rather than shown as zero: a coverage of 0% on a screen about one's own
 * measurements reads as «you answered nothing», and the truth is that this screen could not ask.
 */
internal fun coverageWord(answered: Int, total: Int, failed: Boolean): String = when {
    failed -> "Счётчик ответов не загрузился — полосам профиля он не мешает."
    total == 0 -> "Вопросов анкеты сейчас нет, поэтому заполнять нечего."
    answered == 0 -> "Из $total вопросов анкеты вы не ответили ни на один."
    answered >= total -> "Анкета закрыта: $answered ${answersWord(answered)} из $total."
    else -> "У вас $answered ${answersWord(answered)} из $total вопросов."
}

/**
 * What the profile is made of, said in positions rather than in bands.
 *
 * Zero is described as an absence here too: «0 измеренных позиций» under a heading about the
 * profile would read as a measurement of nothing, which is a claim the engine never made.
 */
internal fun measuredWord(count: Int): String = when {
    count == 0 -> "Профиль ещё не собран: измеренных позиций нет."
    count == 1 -> "1 измеренная позиция, и каждая полоса — среднее тех, что под ней."
    else -> "$count ${positionsWord(count)} — и каждая полоса сложена из тех, что под ней."
}

private fun positionsWord(count: Int): String = when {
    count % 100 in 11..14 -> "позиций"
    count % 10 == 1 -> "позиция"
    count % 10 in 2..4 -> "позиции"
    else -> "позиций"
}

/** The one sentence the axis disclosure is given by, so the card does not repeat it per band. */
internal fun axisGlossHint(): String =
    "Полоса — среднее измеренных позиций; раскройте её, чтобы увидеть каждую."

/**
 * When the engine last rebuilt this profile from this person's answers, as the device reads that
 * moment. Null when the server gave no moment at all — a screen about one's own measurements must
 * not invent a date for when they changed.
 */
internal fun updatedAtWord(iso: String?, zone: ZoneId = ZoneId.systemDefault()): String? {
    val at = iso?.let {
        runCatching { OffsetDateTime.parse(it).atZoneSameInstant(zone) }.getOrNull()
    } ?: return null
    return "Обновлён " + at.format(
        DateTimeFormatter.ofPattern("d MMMM yyyy 'в' HH:mm", Locale("ru")),
    )
}

/** What is still missing in one section, in the counts the server itself returned. */
internal fun sectionGapWord(section: CategoryProgress): String = when {
    section.total == 0 -> "Раздел «${section.label}» сейчас без вопросов."
    section.answered == 0 ->
        "«${section.label}»: раздел не начат — ${section.total} ${answersWord(section.total)} без ответа."
    else ->
        "«${section.label}»: ${section.answered} из ${section.total}, " +
            "${section.total - section.answered} ${answersWord(section.total - section.answered)} ещё не дано."
}

internal fun gapCtaWord(section: CategoryProgress): String =
    if (section.answered == 0) "Пройти «${section.label}»" else "Продолжить «${section.label}»"
