package app.befos.presentation.test

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.LoadingBox
import app.befos.core.designsystem.MessagePane
import app.befos.core.di.beFosViewModel
import app.befos.presentation.common.CategoryScoreList

@Composable
fun TestScreen(onFinished: () -> Unit) {
    val vm: TestViewModel = beFosViewModel { TestViewModel(it.testRepository) }
    val state by vm.uiState.collectAsState()

    when {
        state.loading -> LoadingBox()
        state.error != null && state.questions.isEmpty() -> MessagePane(
            text = state.error ?: "Ошибка",
            title = "Не удалось загрузить тест",
            actionLabel = "Повторить",
            onAction = vm::load,
        )
        state.result != null -> TestResultView(state, onFinished)
        else -> TestQuestionView(state, vm)
    }
}

@Composable
private fun TestQuestionView(state: TestUiState, vm: TestViewModel) {
    val question = state.current ?: return
    val haptics = LocalHapticFeedback.current
    val animatedProgress by animateFloatAsState(state.progress, tween(350), label = "testProgress")
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        LinearProgressIndicator(
            progress = { animatedProgress },
            modifier = Modifier.fillMaxWidth().height(6.dp),
        )
        Text(
            "Вопрос ${state.index + 1} из ${state.questions.size}",
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        AnimatedContent(
            targetState = question.id,
            transitionSpec = {
                (slideInHorizontally { it / 4 } + fadeIn()) togetherWith
                    (slideOutHorizontally { -it / 4 } + fadeOut())
            },
            label = "questionTransition",
        ) { targetId ->
            val target = state.questions.firstOrNull { it.id == targetId } ?: return@AnimatedContent
            Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text(target.text, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    target.options.forEach { option ->
                        Card(
                            onClick = {
                                haptics.performHapticFeedback(HapticFeedbackType.LongPress)
                                vm.select(option.id)
                            },
                            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                            elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(
                                option.text,
                                style = MaterialTheme.typography.bodyLarge,
                                modifier = Modifier.padding(16.dp),
                            )
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
            Text(state.error!!, color = MaterialTheme.colorScheme.error, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
        }
    }
}

@Composable
private fun TestResultView(state: TestUiState, onFinished: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Профиль совместимости готов", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text(
            "Так алгоритм видит ваши ответы по семи категориям. Эти же категории используются для расчёта совместимости с другими людьми.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        CategoryScoreList(state.result ?: emptyList())
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            Button(onClick = onFinished, modifier = Modifier.height(52.dp)) {
                Text("Перейти к подбору", fontWeight = FontWeight.SemiBold)
            }
        }
    }
}
