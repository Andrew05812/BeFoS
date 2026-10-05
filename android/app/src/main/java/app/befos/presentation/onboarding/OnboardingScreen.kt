package app.befos.presentation.onboarding

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.togetherWith
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.OffsetMapping
import androidx.compose.ui.text.input.TransformedText
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.Ember
import app.befos.core.designsystem.EmberDeep
import app.befos.core.designsystem.EmberSoft
import app.befos.core.designsystem.Elev
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.tabularDigits
import app.befos.core.di.beFosViewModel
import app.befos.presentation.common.DatingGoalLabels
import app.befos.presentation.common.GenderLabels

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun OnboardingScreen(onDone: () -> Unit) {
    val vm: OnboardingViewModel = beFosViewModel { OnboardingViewModel(it.profileRepository) }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.done) { if (state.done) onDone() }

    val animatedProgress by animateFloatAsState((state.step + 1) / 3f, tween(Motion.Slow), label = "onboardingProgress")

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            // The inset belongs here, not on the scrollable box below: «Далее» is pinned
            // outside that box, so padding the box only squeezed the form while the
            // keyboard stayed on top of the button that submits it.
            .imePadding()
            // Without the gesture bar the pinned «Далее» row sits under it at rest,
            // which the keyboard fix alone does not solve.
            .navigationBarsPadding()
            .padding(horizontal = Spacing.gutter),
    ) {
        // Segmented stepper instead of a bare progress bar.
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = Spacing.lg, bottom = Spacing.xl),
            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            repeat(3) { i ->
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .height(5.dp)
                        .clip(CircleShape)
                        .background(
                            if (i <= state.step) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.surfaceVariant,
                        ),
                )
            }
        }

        Box(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState()),
        ) {
            AnimatedContent(
                targetState = state.step,
                transitionSpec = {
                    val forward = targetState > initialState
                    val enter = slideInHorizontally { if (forward) it / 4 else -it / 4 } +
                        androidx.compose.animation.fadeIn(tween(Motion.Base))
                    val exit = slideOutHorizontally { if (forward) -it / 4 else it / 4 } +
                        androidx.compose.animation.fadeOut(tween(Motion.Fast))
                    enter togetherWith exit
                },
                label = "onboardingStep",
            ) { step ->
                Column(verticalArrangement = Arrangement.spacedBy(Spacing.xl)) {
                    Text(
                        text = "ШАГ ${step + 1} ИЗ 3",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        text = when (step) {
                            0 -> "Расскажите о себе"
                            1 -> "Кого вы ищете"
                            else -> "Что вы любите"
                        },
                        style = MaterialTheme.typography.headlineLarge,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onBackground,
                    )
                    Text(
                        text = when (step) {
                            0 -> "Эти данные видны другим участникам."
                            1 -> "Параметры влияют на то, кого показывает подбор."
                            else -> "По интересам мы предлагаем совместные активности и строим объяснимый подбор."
                        },
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    when (step) {
                        0 -> StepAbout(state, vm)
                        1 -> StepPreferences(state, vm)
                        2 -> StepInterests(state, vm)
                    }
                }
            }
        }

        // Pinned above the button that refused the step. The form is taller than the viewport,
        // so an error rendered at the end of the scrollable column stays off screen and the tap
        // reads as a dead button.
        state.error?.let { InlineNotice(it, modifier = Modifier.padding(bottom = Spacing.md)) }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(vertical = Spacing.xl),
            horizontalArrangement = Arrangement.spacedBy(Spacing.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (state.step > 0) {
                TextButton(onClick = vm::back) { Text("Назад") }
            }
            AppButton(
                text = if (state.step == 2) "Завершить" else "Далее",
                onClick = vm::next,
                loading = state.submitting,
                modifier = Modifier
                    .weight(1f)
                    .height(52.dp),
            )
        }
    }
}

@Composable
private fun StepAbout(state: OnboardingUiState, vm: OnboardingViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.lg)) {
        AppTextField(
            value = state.name,
            onValueChange = vm::onNameChange,
            label = "Имя",
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
            modifier = Modifier.fillMaxWidth(),
        )
        AppTextField(
            value = state.birthDate,
            onValueChange = vm::onBirthDateChange,
            label = "Дата рождения",
            placeholder = "ГГГГ-ММ-ДД",
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number, imeAction = ImeAction.Next),
            visualTransformation = BirthDateMask,
            modifier = Modifier.fillMaxWidth(),
        )
        AppTextField(
            value = state.city,
            onValueChange = vm::onCityChange,
            label = "Город",
            modifier = Modifier.fillMaxWidth(),
        )
        Text(
            text = "ПОЛ",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        SingleChoiceRow(options = GenderLabels, selected = state.gender, onSelect = vm::setGender)
        AppTextField(
            value = state.about,
            onValueChange = vm::onAboutChange,
            label = "О себе",
            singleLine = false,
            minLines = 3,
            maxLines = 5,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun StepPreferences(state: OnboardingUiState, vm: OnboardingViewModel) {
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.lg)) {
        Text(
            text = "ЦЕЛЬ ЗНАКОМСТВА",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        SingleChoiceRow(options = DatingGoalLabels, selected = state.datingGoal, onSelect = vm::setDatingGoal)

        Text(
            text = "ВОЗРАСТНОЙ ДИАПАЗОН · ${state.ageMin}–${state.ageMax}",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        androidx.compose.material3.RangeSlider(
            value = state.ageMin.toFloat()..state.ageMax.toFloat(),
            onValueChange = { r -> vm.setAgeRange(r.start.toInt(), r.endInclusive.toInt()) },
            valueRange = 18f..99f,
            steps = 80,
        )

        Text(
            text = "ПОКАЗЫВАТЬ ПРОФИЛИ",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(Spacing.sm), verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            GenderLabels.forEach { (code, label) ->
                InterestChip(
                    label = label,
                    selected = state.genderPreference.contains(code),
                    onClick = { vm.toggleGenderPreference(code) },
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
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.lg)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            Text(
                text = "ВЫБЕРИТЕ МИНИМУМ 3",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Box(
                modifier = Modifier
                    .clip(CircleShape)
                    .background(
                        if (state.selectedInterests.size >= 3) EmberSoft
                        else MaterialTheme.colorScheme.surfaceVariant,
                    )
                    .padding(horizontal = Spacing.md, vertical = 2.dp),
            ) {
                Text(
                    text = if (state.selectedInterests.size >= 3) {
                        "Выбрано ${state.selectedInterests.size}"
                    } else {
                        "${state.selectedInterests.size} / 3"
                    },
                    style = MaterialTheme.typography.labelLarge.tabularDigits(),
                    color = if (state.selectedInterests.size >= 3) {
                        EmberDeep
                    } else {
                        MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
            }
        }
        if (state.interestsLoading) {
            Box(Modifier.fillMaxWidth().padding(Spacing.huge), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(Spacing.sm), verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                state.interests.forEach { interest ->
                    InterestChip(
                        label = interest.name,
                        selected = state.selectedInterests.contains(interest.slug),
                        onClick = { vm.toggleInterest(interest.slug) },
                    )
                }
            }
        }
    }
}

/** Full-width single-choice rows: selected gets the iris signature + dot. */
@Composable
private fun SingleChoiceRow(
    options: Map<String, String>,
    selected: String,
    onSelect: (String) -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        options.forEach { (code, label) ->
            val isSel = code == selected
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(MaterialTheme.shapes.small)
                    .background(
                        if (isSel) EmberSoft
                        else MaterialTheme.colorScheme.surface,
                    )
                    .border(
                        Elev.hairlineWidth,
                        if (isSel) Ember.copy(alpha = 0.5f)
                        else MaterialTheme.colorScheme.outlineVariant,
                        MaterialTheme.shapes.small,
                    )
                    .clickable { onSelect(code) }
                    .padding(horizontal = Spacing.lg, vertical = Spacing.md),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(Spacing.md),
            ) {
                Box(
                    modifier = Modifier
                        .size(20.dp)
                        .clip(CircleShape)
                        .border(1.5.dp, if (isSel) Ember else MaterialTheme.colorScheme.outline, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    if (isSel) {
                        Box(Modifier.size(10.dp).clip(CircleShape).background(Ember))
                    }
                }
                Text(
                    label,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = if (isSel) FontWeight.SemiBold else FontWeight.Normal,
                    color = if (isSel) EmberDeep else MaterialTheme.colorScheme.onSurface,
                )
            }
        }
    }
}

/**
 * The field stores digits only, so a numeric keyboard is enough to enter a date:
 * separators are drawn on top of the text and never become part of the value.
 */
private object BirthDateMask : VisualTransformation {
    override fun filter(text: AnnotatedString): TransformedText {
        val digits = text.text
        val shown = StringBuilder()
        val caretToDisplay = IntArray(digits.length + 1)
        digits.forEachIndexed { index, digit ->
            if ((index == 4 || index == 6) && digits.length > index) shown.append('-')
            caretToDisplay[index] = shown.length
            shown.append(digit)
        }
        caretToDisplay[digits.length] = shown.length
        val display = shown.toString()
        return TransformedText(
            AnnotatedString(display),
            object : OffsetMapping {
                override fun originalToTransformed(offset: Int) = caretToDisplay[offset.coerceIn(0, digits.length)]
                override fun transformedToOriginal(offset: Int): Int {
                    val position = offset.coerceIn(0, display.length)
                    var best = 0
                    for (index in caretToDisplay.indices) {
                        if (caretToDisplay[index] <= position) best = index else break
                    }
                    return best
                }
            },
        )
    }
}
