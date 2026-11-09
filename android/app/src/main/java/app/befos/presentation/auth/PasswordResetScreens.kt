package app.befos.presentation.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.Spacing
import app.befos.core.di.beFosViewModel

/**
 * The two halves of getting back in, as two destinations.
 *
 * They are split because the person using them leaves the middle: the first screen ends with a
 * question about a mailbox, and the answer arrives somewhere else, on another app, sometimes after
 * minutes. A single screen with a stage inside it would have to hold the code across that detour,
 * and a person who came back to a form that forgot what it was asking is not helped by the flow
 * having been shorter.
 *
 * The copy is written to the claim the server can support. Nothing here says a letter arrived:
 * `letterSent` means the request was accepted, and the answer is deliberately the same for an address
 * that holds no account — so the screen cannot tell anybody who signs up here either.
 */
@Composable
fun PasswordResetRequestScreen(
    onBack: () -> Unit,
    onLetterSent: () -> Unit,
) {
    val vm: PasswordResetViewModel = beFosViewModel { PasswordResetViewModel(it.authRepository) }
    val state by vm.uiState.collectAsState()

    androidx.compose.runtime.LaunchedEffect(state.letterSent) {
        if (state.letterSent) onLetterSent()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .navigationBarsPadding()
            .padding(horizontal = Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        Text(
            text = "Возврат доступа",
            style = MaterialTheme.typography.headlineMedium,
            modifier = Modifier.padding(top = Spacing.xl),
        )
        Text(
            text = "Введите адрес, с которого вы входили. Мы отправим код, который примет одно " +
                "попытку и перестанет работать через несколько минут.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        AppTextField(
            value = state.email,
            onValueChange = vm::onEmailChange,
            label = "Email",
            singleLine = true,
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Email,
                imeAction = ImeAction.Next,
            ),
        )
        state.error?.let { InlineNotice(it) }
        AppButton(
            text = "Отправить код",
            onClick = vm::requestLetter,
            loading = state.busy,
            modifier = Modifier.fillMaxWidth(),
        )
        AppButton(
            text = "Назад",
            onClick = onBack,
            secondary = true,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
fun PasswordResetCodeScreen(
    onBack: () -> Unit,
    onDone: () -> Unit,
) {
    val vm: PasswordResetViewModel = beFosViewModel { PasswordResetViewModel(it.authRepository) }
    val state by vm.uiState.collectAsState()

    androidx.compose.runtime.LaunchedEffect(state.done) {
        if (state.done) onDone()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .navigationBarsPadding()
            .padding(horizontal = Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = "Код из письма",
            style = MaterialTheme.typography.headlineMedium,
            modifier = Modifier.padding(top = Spacing.xl),
        )
        Text(
            text = "Код состоит из двенадцати знаков и читается по четыре: ABCD-EFGH-JKLM. " +
                "Можно вводить без разделителей.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        AppTextField(
            value = state.code,
            onValueChange = vm::onCodeChange,
            label = "Код из письма",
            singleLine = true,
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Ascii,
                imeAction = ImeAction.Next,
            ),
        )
        AppTextField(
            value = state.newPassword,
            onValueChange = vm::onNewPasswordChange,
            label = "Новый пароль",
            isPassword = true,
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
        )
        AppTextField(
            value = state.passwordConfirm,
            onValueChange = vm::onConfirmChange,
            label = "Повторите пароль",
            isPassword = true,
            singleLine = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            onImeAction = vm::spendCode,
        )
        state.error?.let { InlineNotice(it) }
        AppButton(
            text = "Сменить пароль",
            onClick = vm::spendCode,
            loading = state.busy,
            modifier = Modifier.fillMaxWidth(),
        )
        Text(
            text = "Если код не подошёл, вернитесь и запросите письмо заново.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        AppButton(
            text = "Назад",
            onClick = onBack,
            secondary = true,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}
