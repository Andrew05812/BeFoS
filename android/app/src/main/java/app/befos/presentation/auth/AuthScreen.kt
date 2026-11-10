package app.befos.presentation.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
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
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.EmberGradient
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.Iris
import app.befos.core.designsystem.Peach
import app.befos.core.designsystem.Spacing
import app.befos.core.di.appContainer
import app.befos.core.di.beFosViewModel

@Composable
fun AuthScreen(onAuthed: () -> Unit, onForgotPassword: () -> Unit) {
    val container = appContainer()
    val vm: AuthViewModel = beFosViewModel {
        AuthViewModel(it.authRepository, it.referralRepository)
    }
    val state by vm.uiState.collectAsState()
    val carriedInvite by container.registrationInviteCode.collectAsState()

    // A link opened in this process is offered to the form, not forced on it: the banner can be
    // dismissed and the account made without one. The code leaves the container only on success or
    // on an explicit refusal, so a recomposition does not lose it halfway through typing.
    LaunchedEffect(carriedInvite) {
        carriedInvite?.let(vm::offerInvitation)
    }

    LaunchedEffect(state.success) {
        if (state.success) {
            container.clearRegistrationInvite()
            onAuthed()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .imePadding()
            // This screen is not a Scaffold, so the last row — the sign-up/sign-in toggle —
            // otherwise stops at the window edge and sits under the navigation bar.
            .navigationBarsPadding()
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

        state.invitation?.let { invitation ->
            InvitationBanner(
                invitation = invitation,
                onDecline = {
                    container.clearRegistrationInvite()
                    vm.declineInvitation()
                },
                modifier = Modifier.padding(bottom = Spacing.lg),
            )
        }

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
                onImeAction = vm::submit,
                modifier = Modifier.fillMaxWidth(),
            )
            if (state.isRegister) {
                AppTextField(
                    value = state.passwordConfirm,
                    onValueChange = vm::onPasswordConfirmChange,
                    label = "Повторите пароль",
                    isPassword = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                    onImeAction = vm::submit,
                    modifier = Modifier.fillMaxWidth(),
                )
                // Stage 131: an account is made by a person who has read what it is for and where
                // the data goes. The text is the server's current document, and the version the
                // box carries is what the register door records on the row.
                ConsentPanel(
                    document = state.consent,
                    checked = state.consentChecked,
                    onCheckedChange = vm::onConsentChecked,
                    loading = state.consentLoading,
                    error = state.consentError,
                )
            }
            state.error?.let { InlineNotice(it) }
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
            TextButton(
                onClick = {
                    // Walking to the login branch is a refusal of the invitation, not a detour.
                    container.clearRegistrationInvite()
                    vm.toggleMode()
                },
            ) {
                Text(
                    if (state.isRegister) "Войти" else "Регистрация",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                )
            }
            // Only on the login branch, and only ever a question: this row is the bottom of the
            // screen, and asking for a letter is the one thing a person outside their account can
            // still do here. Registration does not need it — nobody has a word to lose yet.
            if (!state.isRegister) {
                TextButton(onClick = onForgotPassword) {
                    Text(
                        "Забыли пароль?",
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                    )
                }
            }
        }
    }
}

/**
 * The words a forwarded door gets on the form it opens.
 *
 * None of the four states prints the code: it is a bearer secret, and the inviter's name, id and
 * address are not in the preview either. An expired link and an unreachable server both keep
 * the form usable — the one action a stuck person needs is «create the account anyway».
 */
@Composable
private fun InvitationBanner(
    invitation: Invitation,
    onDecline: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val title: String
    val body: String
    when {
        invitation.checking -> {
            title = "Проверяем приглашение…"
            body = "Форма уже открыта: ответ сервера только скажет, засчитается ли ссылка."
        }
        invitation.valid == true -> {
            title = "Вас пригласили в BeFoS"
            body = invitation.expiresAt?.let { expires ->
                "Личная ссылка друга действует до ${inviteDate(expires)}. Она одноразовая и " +
                    "закроется после регистрации."
            } ?: "Личная ссылка друга одноразовая и закроется после регистрации."
        }
        invitation.valid == false -> {
            title = "Приглашение больше не действует"
            body = "Ссылку уже использовали или её срок истёк. Это не мешает создать аккаунт — " +
                "просто регистрация будет без приглашения."
        }
        else -> {
            title = "Приглашение не проверилось"
            body = "Проверка не прошла, но форма работает: сервер попробует применить код при " +
                "регистрации. Если ссылка была действующей, она закроется."
        }
    }

    AppCard(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.lg),
            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            Text(
                "Приглашение друга",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.primary,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Text(
                body,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            TextButton(onClick = onDecline) {
                Text(
                    "Продолжить без приглашения",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                )
            }
        }
    }
}

/** `2026-12-09T23:59:59+03:00` is a date on a banner, not a parser exercise. */
private fun inviteDate(value: String): String =
    value.take(10).replace("-", ".")
