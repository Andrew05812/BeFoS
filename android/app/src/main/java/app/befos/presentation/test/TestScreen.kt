package app.befos.presentation.test

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
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
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.EmberGradient
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.TestSkeleton
import app.befos.core.designsystem.rememberHaptics
import app.befos.core.di.beFosViewModel
import app.befos.presentation.common.CategoryScoreList

@Composable
fun TestScreen(onFinished: () -> Unit) {
    val vm: TestViewModel = beFosViewModel { TestViewModel(it.testRepository) }
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
                Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                    target.options.forEachIndexed { i, option ->
                        AppCard(
                            modifier = Modifier
                                .fillMaxWidth()
                                .heightIn(min = 64.dp),
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
                                        .background(MaterialTheme.colorScheme.surfaceVariant)
                                        .border(1.dp, MaterialTheme.colorScheme.outlineVariant, CircleShape),
                                    contentAlignment = Alignment.Center,
                                ) {
                                    Text(
                                        ('А' + i).toString(),
                                        style = MaterialTheme.typography.labelLarge,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                                Text(
                                    option.text,
                                    style = MaterialTheme.typography.bodyLarge,
                                    color = MaterialTheme.colorScheme.onSurface,
                                )
                            }
                        }
                    }
                }
            }
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
                CategoryScoreList(state.result ?: emptyList())
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
