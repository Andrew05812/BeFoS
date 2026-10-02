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
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.LoadingState
import app.befos.core.designsystem.SectionHeader
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
            LoadingState(Modifier.padding(padding))
            return@Scaffold
        }
        Column(
            modifier = Modifier.padding(padding).fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            AppTextField(state.name, vm::onNameChange, label = "Имя", modifier = Modifier.fillMaxWidth())
            AppTextField(state.city, vm::onCityChange, label = "Город", modifier = Modifier.fillMaxWidth())
            AppTextField(
                state.about,
                vm::onAboutChange,
                label = "О себе",
                singleLine = false,
                minLines = 3,
                maxLines = 5,
                modifier = Modifier.fillMaxWidth(),
            )

            SectionHeader("Пол")
            ChoiceRow(GenderLabels, state.gender, vm::setGender)
            SectionHeader("Цель знакомства")
            ChoiceRow(DatingGoalLabels, state.datingGoal, vm::setDatingGoal)

            SectionHeader("Возрастной диапазон: ${state.ageMin}–${state.ageMax}")
            RangeSlider(
                value = state.ageMin.toFloat()..state.ageMax.toFloat(),
                onValueChange = { r -> vm.setAgeRange(r.start.toInt(), r.endInclusive.toInt()) },
                valueRange = 18f..99f,
                steps = 80,
            )

            SectionHeader("Показывать профили")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GenderLabels.forEach { (code, label) ->
                    InterestChip(
                        label = label,
                        selected = state.genderPreference.contains(code),
                        onClick = { vm.toggleGenderPreference(code) },
                    )
                }
            }

            SectionHeader("Интересы (${state.selectedInterests.size})")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                state.allInterests.forEach { interest ->
                    InterestChip(
                        label = interest.name,
                        selected = state.selectedInterests.contains(interest.slug),
                        onClick = { vm.toggleInterest(interest.slug) },
                    )
                }
            }

            if (state.error != null) {
                Text(state.error!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
            }

            AppButton(text = "Сохранить", onClick = vm::save, loading = state.saving, modifier = Modifier.fillMaxWidth())
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChoiceRow(options: Map<String, String>, selected: String, onSelect: (String) -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { (code, label) ->
            InterestChip(label = label, selected = code == selected, onClick = { onSelect(code) })
        }
    }
}
