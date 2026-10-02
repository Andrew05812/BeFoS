package app.befos.presentation.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTopBar
import app.befos.core.di.beFosViewModel

@Composable
fun SettingsScreen(onBack: () -> Unit, onLoggedOut: () -> Unit) {
    val vm: SettingsViewModel = beFosViewModel { SettingsViewModel(it.safetyRepository, it.authRepository) }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.loggedOut, state.deleted) {
        if (state.loggedOut || state.deleted) onLoggedOut()
    }

    if (state.confirmDelete) {
        AlertDialog(
            onDismissRequest = vm::cancelDelete,
            title = { Text("Удалить аккаунт?") },
            text = { Text("Это действие необратимо: профиль, пары и сообщения будут удалены.") },
            confirmButton = { TextButton(onClick = vm::deleteAccount) { Text("Удалить", color = MaterialTheme.colorScheme.error) } },
            dismissButton = { TextButton(onClick = vm::cancelDelete) { Text("Отмена") } },
        )
    }

    Scaffold(
        topBar = { AppTopBar(title = "Настройки", onBack = onBack) },
    ) { padding ->
        Column(
            modifier = Modifier.padding(padding).fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            AppCard(modifier = Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text("Скрыть из подбора", style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
                        Text(
                            "Вас не будут показывать новым людям, но существующие пары сохранятся.",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Switch(checked = state.hidden, onCheckedChange = vm::setHidden, enabled = !state.busy)
                }
            }

            if (state.message != null) {
                Text(state.message!!, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            OutlinedButton(onClick = vm::logout, modifier = Modifier.fillMaxWidth().height(52.dp)) {
                Text("Выйти из аккаунта")
            }
            OutlinedButton(
                onClick = vm::askDelete,
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) {
                Text("Удалить аккаунт", color = MaterialTheme.colorScheme.error)
            }
        }
    }
}
