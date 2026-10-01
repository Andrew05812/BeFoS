package app.befos.presentation.editprofile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RangeSlider
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.LoadingBox
import app.befos.core.di.beFosViewModel
import app.befos.presentation.common.DatingGoalLabels
import app.befos.presentation.common.GenderLabels

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun EditProfileScreen(onBack: () -> Unit) {
    val vm: EditProfileViewModel = beFosViewModel { EditProfileViewModel(it.profileRepository) }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.saved) { if (state.saved) onBack() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Профиль", fontWeight = FontWeight.SemiBold) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад") }
                },
            )
        },
    ) { padding ->
        if (state.loading) {
            LoadingBox(Modifier.padding(padding))
            return@Scaffold
        }
        Column(
            modifier = Modifier.padding(padding).fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            OutlinedTextField(state.name, vm::onNameChange, label = { Text("Имя") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(state.city, vm::onCityChange, label = { Text("Город") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            OutlinedTextField(state.about, vm::onAboutChange, label = { Text("О себе") }, minLines = 3, modifier = Modifier.fillMaxWidth())

            Text("Пол", style = MaterialTheme.typography.titleSmall)
            ChoiceRow(GenderLabels, state.gender, vm::setGender)
            Text("Цель знакомства", style = MaterialTheme.typography.titleSmall)
            ChoiceRow(DatingGoalLabels, state.datingGoal, vm::setDatingGoal)

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

            Text("Интересы (${state.selectedInterests.size})", style = MaterialTheme.typography.titleSmall)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                state.allInterests.forEach { interest ->
                    FilterChip(
                        selected = state.selectedInterests.contains(interest.slug),
                        onClick = { vm.toggleInterest(interest.slug) },
                        label = { Text(interest.name) },
                    )
                }
            }

            if (state.error != null) {
                Text(state.error!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
            }

            Button(onClick = vm::save, enabled = !state.saving, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                if (state.saving) {
                    CircularProgressIndicator(modifier = Modifier.height(22.dp), color = MaterialTheme.colorScheme.onPrimary, strokeWidth = 2.dp)
                } else {
                    Text("Сохранить", fontWeight = FontWeight.SemiBold)
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ChoiceRow(options: Map<String, String>, selected: String, onSelect: (String) -> Unit) {
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
