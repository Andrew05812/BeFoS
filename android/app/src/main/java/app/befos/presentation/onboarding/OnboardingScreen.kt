package app.befos.presentation.onboarding

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.animation.togetherWith
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RangeSlider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import app.befos.core.di.beFosViewModel
import app.befos.presentation.common.DatingGoalLabels
import app.befos.presentation.common.GenderLabels

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun OnboardingScreen(onDone: () -> Unit) {
    val vm: OnboardingViewModel = beFosViewModel { OnboardingViewModel(it.profileRepository) }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.done) { if (state.done) onDone() }

    val animatedProgress by animateFloatAsState((state.step + 1) / 3f, tween(350), label = "onboardingProgress")

    Column(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        LinearProgressIndicator(
            progress = { animatedProgress },
            modifier = Modifier.fillMaxWidth().height(6.dp),
        )
        AnimatedContent(
            targetState = state.step,
            transitionSpec = {
                val forward = targetState > initialState
                val enter = slideInHorizontally { if (forward) it / 4 else -it / 4 }
                val exit = slideOutHorizontally { if (forward) -it / 4 else it / 4 }
                enter togetherWith exit
            },
            label = "onboardingStep",
        ) { step ->
            Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text(
                    when (step) {
                        0 -> "Расскажите о себе"
                        1 -> "Кого вы ищете"
                        else -> "Ваши интересы"
                    },
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
                when (step) {
                    0 -> StepAbout(state, vm)
                    1 -> StepPreferences(state, vm)
                    2 -> StepInterests(state, vm)
                }
            }
        }

        if (state.error != null) {
            Text(state.error!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
        }

        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            if (state.step > 0) {
                TextButton(onClick = vm::back, modifier = Modifier.weight(1f)) { Text("Назад") }
            }
            Button(
                onClick = vm::next,
                enabled = !state.submitting,
                modifier = Modifier.weight(2f).height(52.dp),
            ) {
                if (state.submitting) {
                    CircularProgressIndicator(modifier = Modifier.height(22.dp), color = MaterialTheme.colorScheme.onPrimary, strokeWidth = 2.dp)
                } else {
                    Text(if (state.step == 2) "Завершить" else "Далее", fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@Composable
private fun StepAbout(state: OnboardingUiState, vm: OnboardingViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        OutlinedTextField(
            value = state.name, onValueChange = vm::onNameChange, label = { Text("Имя") },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = state.birthDate, onValueChange = vm::onBirthDateChange,
            label = { Text("Дата рождения") }, placeholder = { Text("ГГГГ-ММ-ДД") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Next),
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = state.city, onValueChange = vm::onCityChange, label = { Text("Город") },
            singleLine = true, modifier = Modifier.fillMaxWidth(),
        )
        Text("Пол", style = MaterialTheme.typography.titleSmall)
        SingleChoiceRow(options = GenderLabels, selected = state.gender, onSelect = vm::setGender)
        OutlinedTextField(
            value = state.about, onValueChange = vm::onAboutChange, label = { Text("О себе") },
            minLines = 3, modifier = Modifier.fillMaxWidth(),
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun StepPreferences(state: OnboardingUiState, vm: OnboardingViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Цель знакомства", style = MaterialTheme.typography.titleSmall)
        SingleChoiceRow(options = DatingGoalLabels, selected = state.datingGoal, onSelect = vm::setDatingGoal)

        Text("Возрастной диапазон: ${state.ageMin}–${state.ageMax}", style = MaterialTheme.typography.titleSmall)
        RangeSlider(
            value = state.ageMin.toFloat()..state.ageMax.toFloat(),
            onValueChange = { r -> vm.setAgeRange(r.start.toInt(), r.endInclusive.toInt()) },
            valueRange = 18f..99f,
            steps = 80,
        )

        Text("Показывать профили", style = MaterialTheme.typography.titleSmall)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            GenderLabels.forEach { (code, label) ->
                FilterChip(
                    selected = state.genderPreference.contains(code),
                    onClick = { vm.toggleGenderPreference(code) },
                    label = { Text(label) },
                )
            }
        }
        if (state.genderPreference.isEmpty()) {
            Text(
                "Если не выбрать — подойдут все",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun StepInterests(state: OnboardingUiState, vm: OnboardingViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            "Выберите минимум 3 (${state.selectedInterests.size})",
            style = MaterialTheme.typography.titleSmall,
        )
        if (state.interestsLoading) {
            Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                state.interests.forEach { interest ->
                    FilterChip(
                        selected = state.selectedInterests.contains(interest.slug),
                        onClick = { vm.toggleInterest(interest.slug) },
                        label = { Text(interest.name) },
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SingleChoiceRow(
    options: Map<String, String>,
    selected: String,
    onSelect: (String) -> Unit,
) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { (code, label) ->
            AssistChip(
                onClick = { onSelect(code) },
                label = { Text(label) },
                colors = if (code == selected) {
                    AssistChipDefaults.assistChipColors(
                        containerColor = MaterialTheme.colorScheme.primaryContainer,
                        labelColor = MaterialTheme.colorScheme.onPrimaryContainer,
                    )
                } else {
                    AssistChipDefaults.assistChipColors()
                },
            )
        }
    }
}
