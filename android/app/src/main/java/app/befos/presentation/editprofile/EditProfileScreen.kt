package app.befos.presentation.editprofile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RangeSlider
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.ProfileSkeleton
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.di.beFosViewModel
import app.befos.presentation.common.DatingGoalLabels
import app.befos.presentation.common.GenderLabels

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun EditProfileScreen(onBack: () -> Unit) {
    val vm: EditProfileViewModel = beFosViewModel { EditProfileViewModel(it.profileRepository) }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.saved) { if (state.saved) onBack() }

    Scaffold(
        topBar = { AppTopBar(title = "Профиль", onBack = onBack) },
    ) { padding ->
        if (state.loading) {
            ProfileSkeleton(Modifier.padding(padding))
            return@Scaffold
        }
        if (state.loadFailed) {
            ErrorState(
                message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
                title = "Профиль не загрузился",
                onRetry = vm::load,
                modifier = Modifier.padding(padding),
            )
            return@Scaffold
        }
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .imePadding()
                .padding(horizontal = Spacing.gutter, vertical = Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.xxl),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("Основные данные")
                AppCard(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.padding(Spacing.xl),
                        verticalArrangement = Arrangement.spacedBy(Spacing.md),
                    ) {
                        AppTextField(
                            value = state.name,
                            onValueChange = vm::onNameChange,
                            label = "Имя",
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                            modifier = Modifier.fillMaxWidth(),
                        )
                        AppTextField(
                            value = state.city,
                            onValueChange = vm::onCityChange,
                            label = "Город",
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
                            modifier = Modifier.fillMaxWidth(),
                        )
                        AppTextField(
                            state.about,
                            vm::onAboutChange,
                            label = "О себе",
                            singleLine = false,
                            minLines = 3,
                            maxLines = 5,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("Кого вы ищете")
                Text("Ваш пол", style = MaterialTheme.typography.titleSmall)
                ChoiceRow(GenderLabels, state.gender, vm::setGender)
                Text("Цель знакомства", style = MaterialTheme.typography.titleSmall)
                ChoiceRow(DatingGoalLabels, state.datingGoal, vm::setDatingGoal)
                Text(
                    "Возрастной диапазон: ${state.ageMin}–${state.ageMax}",
                    style = MaterialTheme.typography.titleSmall,
                )
                RangeSlider(
                    value = state.ageMin.toFloat()..state.ageMax.toFloat(),
                    onValueChange = { r -> vm.setAgeRange(r.start.toInt(), r.endInclusive.toInt()) },
                    valueRange = 18f..99f,
                    steps = 80,
                )
                Text("Показывать профили", style = MaterialTheme.typography.titleSmall)
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    GenderLabels.forEach { (code, label) ->
                        InterestChip(
                            label = label,
                            selected = state.genderPreference.contains(code),
                            onClick = { vm.toggleGenderPreference(code) },
                        )
                    }
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("Интересы · ${state.selectedInterests.size}")
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    state.allInterests.forEach { interest ->
                        InterestChip(
                            label = interest.name,
                            selected = state.selectedInterests.contains(interest.slug),
                            onClick = { vm.toggleInterest(interest.slug) },
                        )
                    }
                }
                // An empty picker is otherwise indistinguishable from a profile with no
                // interests, and the user would leave without any.
                if (state.interestsFailed) {
                    InlineNotice(
                        "Список интересов не загрузился.",
                        actionLabel = "Повторить",
                        onAction = vm::loadInterests,
                    )
                }
            }

            state.error?.let { InlineNotice(it) }

            AppButton(text = "Сохранить", onClick = vm::save, loading = state.saving, modifier = Modifier.fillMaxWidth())
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChoiceRow(options: Map<String, String>, selected: String, onSelect: (String) -> Unit) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
        verticalArrangement = Arrangement.spacedBy(Spacing.sm),
    ) {
        options.forEach { (code, label) ->
            InterestChip(label = label, selected = code == selected, onClick = { onSelect(code) })
        }
    }
}
