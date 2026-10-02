package app.befos.presentation.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.EmberGradient
import app.befos.core.designsystem.Iris
import app.befos.core.designsystem.Peach
import app.befos.core.designsystem.Spacing
import app.befos.core.di.beFosViewModel

@Composable
fun AuthScreen(onAuthed: () -> Unit) {
    val vm: AuthViewModel = beFosViewModel { AuthViewModel(it.authRepository) }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.success) { if (state.success) onAuthed() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .imePadding()
            .padding(horizontal = Spacing.gutter),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        // Brand header: logomark orb + wordmark.
        Box(
            modifier = Modifier
                .padding(top = 56.dp, bottom = Spacing.xxl)
                .size(84.dp)
                .clip(CircleShape)
                .background(Brush.linearGradient(listOf(Peach, Color(0xFFF0544F), Iris))),
            contentAlignment = Alignment.Center,
        ) {
            Text("B", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Black, color = Color.White)
        }
        Text(
            text = if (state.isRegister) "СОЗДАЙТЕ ПРОФИЛЬ" else "С ВОЗВРАЩЕНИЕМ",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = if (state.isRegister) "Знакомства, объяснимые данными" else "Войдите в BeFoS",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onBackground,
            modifier = Modifier.padding(bottom = Spacing.sm),
        )
        Text(
            text = if (state.isRegister) {
                "Один шаг до подбора — нужен только e-mail и пароль."
            } else {
                "Продолжите с того места, где остановились."
            },
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = Spacing.xxl),
        )

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(MaterialTheme.shapes.large)
                .background(MaterialTheme.colorScheme.surface)
                .padding(Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            AppTextField(
                value = state.email,
                onValueChange = vm::onEmailChange,
                label = "Email",
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
                modifier = Modifier.fillMaxWidth(),
            )
            AppTextField(
                value = state.password,
                onValueChange = vm::onPasswordChange,
                label = "Пароль",
                isPassword = true,
                keyboardOptions = KeyboardOptions(imeAction = if (state.isRegister) ImeAction.Next else ImeAction.Done),
                modifier = Modifier.fillMaxWidth(),
            )
            if (state.isRegister) {
                AppTextField(
                    value = state.passwordConfirm,
                    onValueChange = vm::onPasswordConfirmChange,
                    label = "Повторите пароль",
                    isPassword = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            if (state.error != null) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(MaterialTheme.shapes.extraSmall)
                        .background(MaterialTheme.colorScheme.errorContainer)
                        .padding(horizontal = Spacing.md, vertical = Spacing.sm),
                ) {
                    Text(
                        state.error!!,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
            AppButton(
                text = if (state.isRegister) "Создать аккаунт" else "Войти",
                onClick = vm::submit,
                loading = state.loading,
                modifier = Modifier.fillMaxWidth(),
            )
        }

        Row(
            modifier = Modifier.padding(vertical = Spacing.xxl),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = if (state.isRegister) "Уже с нами?" else "Впервые в BeFoS?",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            TextButton(onClick = vm::toggleMode) {
                Text(
                    if (state.isRegister) "Войти" else "Регистрация",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}
