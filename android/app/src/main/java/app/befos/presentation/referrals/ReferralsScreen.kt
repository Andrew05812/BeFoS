package app.befos.presentation.referrals

import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.rememberHaptics
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.Invite
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.delay

/**
 * The inviter's own screen: one live door, the ones that closed, and how many people walked through.
 *
 * The count is the only thing the inviter learns about an invited person, and that is deliberate —
 * `docs/API.md` states the same rule for the server. A referral screen that showed a name or an
 * address would turn a friend's registration into the inviter's contact list; the product has no
 * use for that and the person never agreed to it.
 */
@Composable
fun ReferralsScreen(onBack: () -> Unit) {
    val vm: ReferralViewModel = beFosViewModel { ReferralViewModel(it.referralRepository) }
    val state by vm.uiState.collectAsState()
    val context = LocalContext.current
    val haptics = rememberHaptics()
    val active = state.active

    LaunchedEffect(state.notice) {
        if (state.notice != null) {
            delay(2400)
            vm.clearNotice()
        }
    }

    state.confirmRevokeId?.let {
        AlertDialog(
            onDismissRequest = vm::cancelRevoke,
            title = { Text("Отозвать ссылку?") },
            text = {
                Text(
                    "Ссылка перестанет открываться у всех, кому вы её отправили. " +
                        "Новую можно будет создать сразу же.",
                )
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        haptics.light()
                        vm.revoke()
                    },
                ) {
                    Text("Отозвать", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = { TextButton(onClick = vm::cancelRevoke) { Text("Оставить") } },
        )
    }

    Scaffold(topBar = { AppTopBar(title = "Пригласить друга", onBack = onBack) }) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .navigationBarsPadding()
                .padding(horizontal = Spacing.gutter, vertical = Spacing.lg),
            verticalArrangement = Arrangement.spacedBy(Spacing.xxl),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                Text(
                    "Личная ссылка",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onBackground,
                )
                Text(
                    "Человек, которому вы её отправите, откроет BeFoS и зарегистрируется с этой " +
                        "ссылкой. Мы скажем «приглашение принято», когда аккаунт появится, — и " +
                        "ничего о нём сами не подскажем.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            when {
                state.loading && state.invites.isEmpty() -> {
                    Text(
                        "Загружаем ссылки…",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                state.error != null && state.invites.isEmpty() -> InlineNotice(
                    text = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
                    actionLabel = "Повторить",
                    onAction = vm::load,
                )
                active == null -> {
                    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                        Text(
                            "Личной ссылки пока нет. Создайте её и отправьте одному человеку — " +
                                "ссылка одноразовая и действует 30 дней.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        AppButton(
                            text = "Создать приглашение",
                            onClick = {
                                haptics.success()
                                vm.createInvite()
                            },
                            loading = state.busy,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
                else -> ActiveInviteCard(
                    invite = active,
                    busy = state.busy,
                    onShare = {
                        val send = Intent(Intent.ACTION_SEND).apply {
                            type = "text/plain"
                            putExtra(Intent.EXTRA_TEXT, vm.shareText(active))
                        }
                        context.startActivity(Intent.createChooser(send, "Отправить приглашение"))
                    },
                    onRevoke = { vm.askRevoke(active.id) },
                )
            }

            // A failed create or revoke leaves the list standing, so the empty-list notice above
            // would never speak. It is placed here rather than replacing the card: the live link is
            // still real, and the person has to be able to copy it before retrying the write.
            val writeError = state.error
            if (writeError != null && state.invites.isNotEmpty()) {
                InlineNotice(text = writeError)
            }

            state.notice?.let { InlineNotice(it, isError = false) }

            AppCard(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(Spacing.xl),
                    verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    Text(
                        "Что будет, если ссылка попадёт не к тому",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        "Ссылка открывается один раз. Отзовите её в любой момент — тогда аккаунт " +
                            "по ней завести не смогут. Код нельзя перебрать или привязать к " +
                            "чужим данным: он случайный и не содержит того, кем вы приглашены.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("Пришли по ссылке", subtitle = "Всего: ${state.acceptedTotal}")
                if (state.acceptedTotal == 0) {
                    Text(
                        "Пока никто. Ссылка ждёт одного человека.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    Text(
                        "Кто это был, экран не знает — сервер не отдаёт ни имя, ни адрес " +
                            "приглашённого. Число выше принадлежит вашему аккаунту, и только оно.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            if (state.history.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                    SectionHeader("История ссылок")
                    state.history.forEach { invite ->
                        InviteHistoryRow(invite)
                    }
                }
            }
        }
    }
}

@Composable
private fun ActiveInviteCard(
    invite: Invite,
    busy: Boolean,
    onShare: () -> Unit,
    onRevoke: () -> Unit,
) {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            Text(
                "Ссылка действует",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                invite.url,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier
                    .fillMaxWidth()
                    .background(
                        MaterialTheme.colorScheme.surfaceVariant,
                        MaterialTheme.shapes.small,
                    )
                    .padding(Spacing.md),
            )
            invite.expiresAt?.let { value ->
                Text(
                    "Закрывается ${humanDate(value)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            AppButton(
                text = "Отправить ссылку",
                onClick = onShare,
                modifier = Modifier.fillMaxWidth(),
            )
            AppButton(
                text = "Отозвать ссылку",
                onClick = onRevoke,
                variant = AppButtonVariant.Ghost,
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun InviteHistoryRow(invite: Invite) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = Spacing.xs),
        horizontalArrangement = Arrangement.spacedBy(Spacing.md),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            statusWord(invite.status),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onBackground,
            modifier = Modifier.weight(1f),
        )
        Text(
            (invite.acceptedAt ?: invite.expiresAt ?: invite.createdAt)?.let(::humanDate).orEmpty(),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

private fun statusWord(status: String): String = when (status) {
    "accepted" -> "Принято"
    "revoked" -> "Отозвано"
    "expired" -> "Истекло"
    else -> "Действует"
}

private fun humanDate(value: String): String = runCatching {
    OffsetDateTime.parse(value)
        .atZoneSameInstant(ZoneId.systemDefault())
        .format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
}.getOrDefault(value.take(10))
