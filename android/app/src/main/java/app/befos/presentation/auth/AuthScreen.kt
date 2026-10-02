package app.befos.presentation.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
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
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppTextField
import app.befos.core.di.beFosViewModel

@Composable
fun AuthScreen(onAuthed: () -> Unit) {
    val vm: AuthViewModel = beFosViewModel { AuthViewModel(it.authRepository) }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.success) { if (state.success) onAuthed() }

    Box(
        modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                if (state.isRegister) "Создать аккаунт" else "С возвращением",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                if (state.isRegister) "Регистрация в BeFoS" else "Войдите, чтобы продолжить",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

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
                    modifier = Modifier.fillMaxWidth(),
                )
            }

            if (state.error != null) {
                Text(state.error!!, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
            }

            AppButton(
                text = if (state.isRegister) "Зарегистрироваться" else "Войти",
                onClick = vm::submit,
                loading = state.loading,
                modifier = Modifier.fillMaxWidth(),
            )

            TextButton(onClick = vm::toggleMode) {
                Text(if (state.isRegister) "Уже есть аккаунт? Войти" else "Нет аккаунта? Зарегистрироваться")
            }
        }
    }
}
