package app.befos.presentation.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AsyncAvatar
import app.befos.core.designsystem.LoadingBox
import app.befos.core.designsystem.MessagePane
import app.befos.core.di.beFosViewModel
import app.befos.presentation.common.goalLabel

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ProfileScreen(
    onEdit: () -> Unit,
    onSettings: () -> Unit,
    onTest: () -> Unit,
    onLoggedOut: () -> Unit,
) {
    val vm: ProfileViewModel = beFosViewModel {
        ProfileViewModel(it.profileRepository, it.testRepository, it.authRepository)
    }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.loggedOut) { if (state.loggedOut) onLoggedOut() }

    when {
        state.loading -> LoadingBox()
        state.profile == null -> MessagePane(
            text = state.error ?: "Ошибка",
            title = "Не удалось загрузить профиль",
            actionLabel = "Повторить",
            onAction = vm::load,
        )
        else -> {
            val profile = state.profile!!
            Column(
                modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    AsyncAvatar(profile.primaryPhoto, size = 84.dp)
                    Column {
                        Text("${profile.name}, ${profile.age}", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                        Text(profile.city, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(goalLabel(profile.datingGoal), style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
                    }
                }

                if (!profile.about.isNullOrBlank()) {
                    Text(profile.about, style = MaterialTheme.typography.bodyLarge)
                }

                TestProgressCard(percent = state.testProgress?.percent ?: 0, completed = state.testProgress?.completed ?: false, onTest = onTest)

                if (profile.interests.isNotEmpty()) {
                    Text("Интересы", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        profile.interests.forEach { interest ->
                            AssistChip(onClick = {}, label = { Text(interest.name) })
                        }
                    }
                }

                Row(horizontalArrangement = Arrangement.spacedBy(12.dp), modifier = Modifier.fillMaxWidth()) {
                    OutlinedButton(onClick = onEdit, modifier = Modifier.weight(1f).height(50.dp)) { Text("Редактировать") }
                    OutlinedButton(onClick = onSettings, modifier = Modifier.weight(1f).height(50.dp)) { Text("Настройки") }
                }
            }
        }
    }
}

@Composable
private fun TestProgressCard(percent: Int, completed: Boolean, onTest: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant),
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Профиль совместимости", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Text("$percent%", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            }
            LinearProgressIndicator(progress = { percent / 100f }, modifier = Modifier.fillMaxWidth().height(8.dp))
            Text(
                if (completed) "Тест пройден. Вы можете пройти его заново, чтобы уточнить ответы." else "Пройдите тест — без него совместимость считается неточно.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Button(onClick = onTest, modifier = Modifier.fillMaxWidth()) {
                Text(if (completed) "Пройти заново" else "Пройти тест")
            }
        }
    }
}
