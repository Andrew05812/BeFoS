package app.befos.presentation.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Logout
import androidx.compose.material.icons.outlined.VisibilityOff
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.Elev
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.ErrorRed
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.Spacing
import app.befos.core.di.beFosViewModel

@Composable
fun SettingsScreen(onBack: () -> Unit, onLoggedOut: () -> Unit) {
    val vm: SettingsViewModel = beFosViewModel { SettingsViewModel(it.safetyRepository, it.authRepository, it.profileRepository) }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.loggedOut, state.deleted) {
        if (state.loggedOut || state.deleted) onLoggedOut()
    }

    LaunchedEffect(state.message) {
        if (state.message != null) {
            kotlinx.coroutines.delay(Motion.Notice.toLong())
            vm.clearMessage()
        }
    }

    if (state.confirmDelete) {
        AlertDialog(
            onDismissRequest = vm::cancelDelete,
            title = { Text("Удалить аккаунт?") },
            text = { Text("Аккаунт удалится сразу. Восстановить его не получится.") },
            confirmButton = { TextButton(onClick = vm::deleteAccount) { Text("Удалить", color = MaterialTheme.colorScheme.error) } },
            dismissButton = { TextButton(onClick = vm::cancelDelete) { Text("Отмена") } },
        )
    }

    Scaffold(
        topBar = { AppTopBar(title = "Настройки", onBack = onBack) },
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Spacing.gutter, vertical = Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.xxl),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("Приватность")
                AppCard(modifier = Modifier.fillMaxWidth()) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(Spacing.xl),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(Spacing.lg),
                    ) {
                        SectionIcon(Icons.Outlined.VisibilityOff, MaterialTheme.colorScheme.onSurfaceVariant)
                        Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text("Скрыть из подбора", style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
                            Text(
                                "Вас не будут показывать новым людям, но существующие пары сохранятся.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        // The visible title lives in the sibling column, so the switch itself
                        // carries no text: without this TalkBack announces it as "switch".
                        Switch(
                            checked = state.hidden,
                            onCheckedChange = vm::setHidden,
                            enabled = !state.busy,
                            modifier = Modifier.semantics { contentDescription = "Скрыть из подбора" },
                        )
                    }
                }
                // An off switch and a hidden profile look the same, so when the server never
                // answered which way it is, the screen has to say the position is unverified.
                if (state.visibilityUnknown) {
                    InlineNotice(
                        "Не удалось проверить, скрыты ли вы из подбора.",
                        actionLabel = "Повторить",
                        onAction = vm::load,
                    )
                }
            }

            state.message?.let { message ->
                InlineNotice(message, isError = state.messageIsError)
            }

            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("Аккаунт")
                AppButton(
                    text = "Выйти из аккаунта",
                    onClick = vm::logout,
                    variant = AppButtonVariant.Tonal,
                    leadingIcon = Icons.Outlined.Logout,
                    modifier = Modifier.fillMaxWidth(),
                )
            }

            // Dangerous actions live in their own visually separated zone.
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("Опасная зона")
                AppCard(modifier = Modifier.fillMaxWidth()) {
                    Box(
                        Modifier
                            .fillMaxWidth()
                            .border(Elev.hairlineWidth, ErrorRed.copy(alpha = 0.35f), MaterialTheme.shapes.medium)
                            .background(ErrorRed.copy(alpha = 0.05f), MaterialTheme.shapes.medium)
                            .padding(Spacing.xl),
                    ) {
                        Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(Spacing.md),
                            ) {
                                SectionIcon(Icons.Outlined.Delete, MaterialTheme.colorScheme.error)
                                Text(
                                    "Удаление аккаунта",
                                    style = MaterialTheme.typography.bodyLarge,
                                    fontWeight = FontWeight.SemiBold,
                                )
                            }
                            Text(
                                "Профиль, пары и переписка будут удалены безвозвратно.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            AppButton(
                                text = "Удалить аккаунт",
                                onClick = vm::askDelete,
                                variant = AppButtonVariant.Ghost,
                                contentColorOverride = MaterialTheme.colorScheme.error,
                                modifier = Modifier.fillMaxWidth(),
                            )
                        }
                    }
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                SectionHeader("О приложении")
                Text(
                    "BeFoS · совместимость по семи категориям. Мы считаем её по анкетам и тесту — это не психологический диагноз.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun SectionIcon(icon: ImageVector, tint: androidx.compose.ui.graphics.Color) {
    Box(
        modifier = Modifier
            .size(40.dp)
            .clip(CircleShape)
            .background(tint.copy(alpha = 0.10f)),
        contentAlignment = Alignment.Center,
    ) {
        androidx.compose.material3.Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(20.dp))
    }
}
