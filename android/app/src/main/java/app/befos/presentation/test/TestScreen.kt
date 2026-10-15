package app.befos.presentation.test

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlin.math.roundToInt
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.Ember
import app.befos.core.designsystem.EmberDeep
import app.befos.core.designsystem.EmberGradient
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.TestSkeleton
import app.befos.core.designsystem.answersWord
import app.befos.core.designsystem.rememberHaptics
import app.befos.core.designsystem.tabularDigits
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Option
import app.befos.domain.model.TestProfile
import app.befos.domain.model.TraitAxis
import app.befos.presentation.common.CategoryScoreRow

@Composable
fun TestScreen(startSection: String? = null, onFinished: () -> Unit) {
    val vm: TestViewModel = beFosViewModel { TestViewModel(it.testRepository, startSection) }
    val state by vm.uiState.collectAsState()

    when {
        state.loading -> TestSkeleton()
        state.error != null && state.questions.isEmpty() -> ErrorState(
            message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
            title = "Не удалось загрузить тест",
            onRetry = vm::load,
        )
        state.result != null -> TestResultView(state, onFinished)
        state.questions.isEmpty() -> ErrorState(
            message = "Мы не получили вопросы для теста. Попробуйте обновить — обычно помогает с первого раза.",
            title = "Тест временно недоступен",
            onRetry = vm::load,
        )
        else -> TestQuestionView(state, vm)
    }
}

@Composable
private fun TestQuestionView(state: TestUiState, vm: TestViewModel) {
    val question = state.current ?: return
    val haptics = rememberHaptics()
    val animatedProgress by animateFloatAsState(state.progress, tween(Motion.Slow), label = "testProgress")
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            // Not a Scaffold, so nothing else keeps the «ВОПРОС / 1 / 21» header out from
            // under the status bar the way the other screens' insets do.
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Spacing.gutter, vertical = Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.xl),
    ) {
        // Progress as movement: counter is the hero, the line is its shadow.
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Bottom,
        ) {
            Column {
                Text(
                    text = "ВОПРОС",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Row(verticalAlignment = Alignment.Bottom) {
                    Text(
                        text = "${state.index + 1}",
                        style = MaterialTheme.typography.displayMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        text = " / ${state.questions.size}",
                        style = MaterialTheme.typography.headlineSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(bottom = 6.dp, start = Spacing.xs),
                    )
                }
            }
            Text(
                text = "${(state.progress * 100).toInt()}%",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(6.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.surfaceVariant),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxWidth(animatedProgress)
                    .height(6.dp)
                    .clip(CircleShape)
                    .background(EmberGradient),
            )
        }

        // Which part of the test this question belongs to, and how much of that part is filled:
        // the whole-test counter above says how far the person has walked, not what is still
        // empty, and a person who answered four questions of one band sees 19% either way.
        state.currentCategory?.let { band ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    band.label.uppercase(),
                    style = MaterialTheme.typography.labelMedium,
                    color = EmberDeep,
                )
                Text(
                    "${band.answered} из ${band.total}",
                    style = MaterialTheme.typography.labelMedium.tabularDigits(),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        // Opened from a compatibility band rather than from the profile: the screen has to say why
        // it is not on question one, or the person reads a mid-test position as a lost place.
        state.openedBand?.let { band ->
            Text(
                sectionOpeningWord(band.label, band.answered, band.total),
                style = MaterialTheme.typography.bodySmall,
                color = EmberDeep,
            )
        }

        // A scoring attempt the server refused because sections are still empty is not a failure to
        // retry: it is the next thing to do. The counts the person's own writes came back with name
        // both the gap and the section to walk into.
        state.openSections.firstOrNull()?.let { first ->
            InlineNotice(
                text = unfinishedWord(
                    answered = state.categories.sumOf { it.answered },
                    total = state.categories.sumOf { it.total },
                    open = state.openSections,
                ),
                actionLabel = continueSectionWord(first),
                onAction = vm::goToFirstOpenSection,
                isError = false,
            )
        }

        // A test that came back with answers says so: without this line the person cannot tell
        // a continued test from one that forgot everything, and the number under the counter is
        // just a position.
        if (state.storedOnArrival > 0 && state.result == null) {
            Text(
                "Продолжаем: на сервере уже ${state.storedOnArrival} ${answersWord(state.storedOnArrival)}.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        state.pendingNotice?.let { notice ->
            // The tap stays on screen while its write is unconfirmed, so the notice is about the
            // record, not about the choice — and «Повторить» re-posts the taps that did not land.
            InlineNotice(
                text = notice,
                actionLabel = "Повторить",
                onAction = vm::retryRecords,
            )
        }

        AnimatedContent(
            targetState = question.id,
            transitionSpec = {
                (slideInHorizontally { it / 4 } + fadeIn(tween(Motion.Base))) togetherWith
                    (slideOutHorizontally { -it / 4 } + fadeOut(tween(Motion.Fast)))
            },
            label = "questionTransition",
        ) { targetId ->
            val target = state.questions.firstOrNull { it.id == targetId } ?: return@AnimatedContent
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.lg)) {
                Text(
                    target.text,
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onBackground,
                )
                // A question whose options are one gradation is set with a thumb; everything else,
                // including a kind this client has not heard of, keeps the stack of cards it has
                // always drawn.
                if (target.isScale && target.options.size > 1) {
                    ScaleAnswer(
                        stops = target.options,
                        heldId = state.answers[target.id],
                        onSettle = { optionId ->
                            haptics.light()
                            vm.slide(optionId)
                        },
                    )
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                        target.options.forEachIndexed { i, option ->
                            // The live choice, not only the one the catalogue came back with: going back
                            // to a question tapped a minute ago must show it answered like any other.
                            val chosen = option.id == state.answers[target.id]
                            AppCard(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .heightIn(min = 64.dp)
                                    .then(
                                        if (chosen) Modifier.border(
                                            1.5.dp, Ember.copy(alpha = 0.55f), MaterialTheme.shapes.medium
                                        ) else Modifier
                                    )
                                    .semantics { selected = chosen },
                                onClick = {
                                    haptics.light()
                                    vm.select(option.id)
                                },
                            ) {
                                Row(
                                    modifier = Modifier.padding(horizontal = Spacing.lg, vertical = Spacing.lg),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.spacedBy(Spacing.md),
                                ) {
                                    Box(
                                        modifier = Modifier
                                            .size(32.dp)
                                            .clip(CircleShape)
                                            .background(
                                                if (chosen) Ember
                                                else MaterialTheme.colorScheme.surfaceVariant
                                            )
                                            .border(
                                                1.dp,
                                                if (chosen) Ember else MaterialTheme.colorScheme.outlineVariant,
                                                CircleShape,
                                            ),
                                        contentAlignment = Alignment.Center,
                                    ) {
                                        Text(
                                            ('А' + i).toString(),
                                            style = MaterialTheme.typography.labelLarge,
                                            color = if (chosen) Color.White else MaterialTheme.colorScheme.onSurfaceVariant,
                                        )
                                    }
                                    Text(
                                        option.text,
                                        style = MaterialTheme.typography.bodyLarge,
                                        fontWeight = if (chosen) FontWeight.SemiBold else FontWeight.Normal,
                                        color = if (chosen) EmberDeep else MaterialTheme.colorScheme.onSurface,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        // The section counts that came back with the person's own writes closed the last short
        // section, so the button below scores from a card which is not the end of the catalogue.
        // Said out loud: «Завершить» on question 3 of 5 would otherwise read as a broken flow, and
        // the numbers it rests on are the ones the server gave, not the position on screen.
        if (state.explainsEarlyFinish) {
            Text(
                closedQuestionnaireWord(
                    answered = state.categories.sumOf { it.answered },
                    total = state.categories.sumOf { it.total },
                ),
                style = MaterialTheme.typography.bodySmall,
                color = EmberDeep,
            )
        }

        // Moving on is asked for, not assumed: a released thumb can still be a level about to be
        // changed, and a card that already holds an answer can be read again without being chosen
        // again. The ask is dimmed while the question holds nothing, because there is nothing to
        // leave with.
        val holdsAnswer = state.answers[question.id] != null
        if (holdsAnswer || (question.isScale && question.options.size > 1)) {
            AppButton(
                text = if (state.finishesOnNext) "Завершить" else "Далее",
                onClick = vm::next,
                enabled = holdsAnswer,
                loading = state.submitting,
                modifier = Modifier.fillMaxWidth(),
            )
        }

        if (state.index > 0) {
            TextButton(onClick = vm::back, modifier = Modifier.fillMaxWidth()) { Text("Назад") }
        }
        if (state.submitting) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                Text("Обрабатываем ответы…", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        if (state.error != null) {
            InlineNotice(state.error!!)
        }
    }
}

@Composable
private fun TestResultView(state: TestUiState, onFinished: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Spacing.gutter, vertical = Spacing.hero),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        Text(
            text = "ТЕСТ ПРОЙДЕН",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            "Профиль совместимости готов",
            style = MaterialTheme.typography.headlineLarge,
            fontWeight = FontWeight.Bold,
        )
        Text(
            "Так алгоритм видит ваши ответы. Совместимость с другими считается по этим же категориям — вместе с общими интересами и целью знакомства.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        AppCard(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(Spacing.xl)) {
                bandsWithAxes(state.result ?: TestProfile()).forEachIndexed { i, (band, axes) ->
                    CategoryScoreRow(band, delayMs = i * 60)
                    if (axes.isNotEmpty()) BandAxes(axes)
                }
            }
        }
        Text(
            text = "Расчёт прозрачный: те же ответы всегда дают тот же профиль.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        AppButton(
            text = "Перейти к подбору",
            onClick = onFinished,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = Spacing.sm),
        )
    }
}

/** A band together with the positions of the questionnaire it is the average of. */
internal data class BandWithAxes(val band: CategoryScore, val axes: List<TraitAxis>)

/**
 * The profile as the card draws it: each band with the positions the engine measured it from.
 *
 * The bands keep the order and the counts the route sent, and the axes only ever sit under their own
 * band. A profile whose server predates the axes comes back with bands and nothing under them, which
 * is what the card printed before this existed — so it prints that rather than an empty disclosure.
 */
internal fun bandsWithAxes(profile: TestProfile): List<BandWithAxes> =
    profile.categories.map { band ->
        BandWithAxes(band, profile.axes.filter { it.category == band.category })
    }

/** One position: the axis the answer was stored on, the percent it holds, and the word the engine reads there. */
internal fun axisLine(axis: TraitAxis): String =
    "${axis.label}: ${(axis.value * 100f).roundToInt()}% — ${axis.side}"

/** What the line under those positions promises, and what it is derived from. */
internal fun axisGlossWord(): String =
    "Полоса — среднее этих позиций, а слово у каждой — то, как алгоритм читает ваш ответ."

/** The ask that opens the positions of one band, and its opposite. */
internal fun axesToggleWord(open: Boolean): String =
    if (open) "Скрыть ответы полосы" else "Показать, из каких ответов полоса"

/**
 * The positions behind one band, opened on a tap.
 *
 * Hidden until asked for because the card is five bands deep already on a 320-point screen, and a
 * person who wants the bands alone gets them; the numbers a tap uncovers are the ones the stripe
 * above was averaged from, in the same percent the universe map prints for the same answer.
 */
@Composable
private fun BandAxes(axes: List<TraitAxis>) {
    var open by remember { mutableStateOf(false) }
    TextButton(
        onClick = { open = !open },
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            text = axesToggleWord(open),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
    AnimatedVisibility(
        visible = open,
        enter = fadeIn(tween(Motion.Base)) + expandVertically(tween(Motion.Base)),
        exit = fadeOut(tween(Motion.Base)) + shrinkVertically(tween(Motion.Base)),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(Spacing.xs),
        ) {
            axes.forEach { axis ->
                Text(
                    text = axisLine(axis),
                    style = MaterialTheme.typography.bodySmall.tabularDigits(),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(
                text = axisGlossWord(),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * The line a section opened from a compatibility band prints, so that a position which is not
 * question one reads as a place the person was sent to rather than a place they lost. It quotes
 * only the counts the catalogue itself came back with. A section with every card marked has
 * nothing left to continue into, so it is described as opened for reading rather than as resumed.
 */
internal fun sectionOpeningWord(label: String, answered: Int, total: Int): String = when {
    total == 0 -> "Раздела «$label» в анкете сейчас нет — открываем с того места, где вы остановились."
    answered >= total ->
        "Раздел «$label» пройден: $total из $total. Открываем его первый вопрос — отсюда можно " +
            "перечитать ответы и поправить их."
    answered == 0 ->
        "Раздел «$label» вы ещё не начинали: в нём $total ${answersWord(total)}. " +
            "Открываем с его первого вопроса."
    else ->
        "Открыли раздел «$label»: у вас $answered ${answersWord(answered)} из $total. " +
            "Продолжаем с первой карточки раздела без ответа."
}

/**
 * The line a refused scoring attempt prints. The route answers only on a full set and its refusal
 * carries a bare count, while the writes that just landed carried the sections — so the sentence is
 * built from those: how far the person has come, and which sections the server still counts short.
 * It promises no partner and no percentage, because both would be units the response never gave.
 */
internal fun unfinishedWord(answered: Int, total: Int, open: List<CategoryProgress>): String {
    val sections = open.joinToString(", ") { "${it.label} — ${it.answered} из ${it.total}" }
    return "Профиля ещё нет: у вас $answered ${answersWord(answered)} из $total. " +
        "Без ответа остаётся: $sections."
}

/** What the button next to that line asks for: the section the person is being sent into. */
internal fun continueSectionWord(band: CategoryProgress): String = "Продолжить «${band.label}»"

/**
 * The line printed when the sections the server counted hold an answer for every question of the
 * questionnaire, while the person is standing before its last card. It says what the counts say and
 * what the button below therefore does; it promises no partner and no percentage, because the route
 * handed back neither.
 */
internal fun closedQuestionnaireWord(answered: Int, total: Int): String =
    "Анкета закрыта: у вас $answered ${answersWord(answered)} из $total, пустых разделов не осталось. " +
        "Кнопка «Завершить» считает профиль прямо отсюда — до последней карточки долистывать не нужно."

/**
 * One gradation, set with a thumb instead of tapped as cards.
 *
 * The stops are the question's own options, in the order the catalogue ships them, so the level a
 * person lands on is the same stored answer a card tap would have left and the engine reads the
 * same value either way. The ends are labelled with the first and last of those options rather than
 * with an invented «меньше / больше»: the client is not told the numbers behind the options, and a
 * direction it guessed would be a claim about a scale it cannot see.
 *
 * Until the person lets go, the thumb is a cursor and not an answer — it starts on a middle stop,
 * nothing is stored, and the line under it says the level is still theirs to set.
 */
@Composable
private fun ScaleAnswer(stops: List<Option>, heldId: Int?, onSettle: (Int) -> Unit) {
    var dragging by remember(stops) { mutableStateOf<Float?>(null) }
    val heldIndex = stops.indexOfFirst { it.id == heldId }
    val value = dragging ?: if (heldIndex >= 0) heldIndex.toFloat() else stops.size / 2f
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
        Slider(
            value = value,
            onValueChange = { dragging = it },
            onValueChangeFinished = {
                val index = value.roundToInt().coerceIn(0, stops.lastIndex)
                dragging = null
                onSettle(stops[index].id)
            },
            valueRange = 0f..(stops.size - 1).toFloat(),
            steps = stops.size - 2,
            // A slider reads its value as a percentage of its range, which says nothing about a
            // gradation whose ends are words: the stop the thumb holds is announced in those words.
            modifier = Modifier
                .fillMaxWidth()
                .semantics {
                    stateDescription = if (heldIndex >= 0) stops[heldIndex].text else "уровень не выбран"
                },
        )
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(Spacing.md)) {
            Text(
                stops.first().text,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Start,
                modifier = Modifier.weight(1f),
            )
            Text(
                stops.last().text,
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.End,
                modifier = Modifier.weight(1f),
            )
        }
        Text(
            if (heldIndex >= 0) stops[heldIndex].text
            else "Проведите по шкале и отпустите на том уровне, который вам ближе.",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = if (heldIndex >= 0) FontWeight.SemiBold else FontWeight.Normal,
            color = if (heldIndex >= 0) EmberDeep else MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
