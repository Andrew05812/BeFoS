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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Logout
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Lock
import androidx.compose.material.icons.outlined.PhoneAndroid
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
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.Avatar
import app.befos.core.designsystem.Elev
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.ErrorRed
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.SkeletonBlock
import app.befos.core.designsystem.Spacing
import app.befos.domain.model.BlockedUser
import app.befos.domain.model.DeviceSession
import app.befos.core.di.beFosViewModel
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun SettingsScreen(onBack: () -> Unit, onLoggedOut: () -> Unit, onOpenModeration: () -> Unit) {
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

    state.confirmUnblock?.let { user ->
        AlertDialog(
            onDismissRequest = vm::cancelUnblock,
            title = { Text("Разблокировать ${user.name}?") },
            // The promise is kept short because it is the part a person is likely to expect and the
            // part that is not true: releasing a block opens the profile again, it does not bring back
            // the pair and the messages the block dissolved.
            text = {
                Text(
                    "Анкета снова станет открытой, и на неё можно ответить. " +
                        "Пара и переписка, которые забрал блок, не вернутся — начать их можно новым лайком."
                )
            },
            confirmButton = { TextButton(onClick = vm::confirmUnblock) { Text("Разблокировать") } },
            dismissButton = { TextButton(onClick = vm::cancelUnblock) { Text("Отмена") } },
        )
    }

    state.confirmEndSession?.let { session ->
        AlertDialog(
            onDismissRequest = vm::cancelEndSession,
            title = { Text(if (session.current) "Завершить сессию на этом устройстве?" else "Завершить сессию?") },
            // What the cut does and does not promise. The row's own refresh is refused from the moment
            // the write lands, so no new session can start on that device; the screen does not claim the
            // device is locked out this second, because a token already handed out is honoured until it
            // expires on its own. When the row is this device's, the dialog says so — the app is about to
            // leave the account, which is not what a person expects from a row they recognised.
            text = {
                Text(
                    if (session.current) {
                        "Это то устройство, с которого вы смотрите список. Приложение выйдет из аккаунта, " +
                            "и войти придётся заново."
                    } else {
                        "${deviceWord(session)} больше не сможет обновить сеанс. Начать его можно только " +
                            "новым входом."
                    }
                )
            },
            confirmButton = {
                TextButton(onClick = vm::confirmEndSession, enabled = !state.sessionsBusy) {
                    Text("Завершить", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = { TextButton(onClick = vm::cancelEndSession) { Text("Отмена") } },
        )
    }

    if (state.confirmEndEvery) {
        AlertDialog(
            onDismissRequest = vm::cancelEndEverySession,
            title = { Text("Завершить все сессии?") },
            // Named devices are not the whole of the list's reach: this write also cuts the rows the
            // screen could not show, which is the point of the door for a lost phone.
            text = {
                Text(
                    "Сеанс не останется ни на одном устройстве, включая это. Список показанных входов " +
                        "может быть неполным — этот жест завершает и те, что на экран не вместились."
                )
            },
            confirmButton = {
                TextButton(onClick = vm::confirmEndEverySession, enabled = !state.sessionsBusy) {
                    Text("Завершить все", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = { TextButton(onClick = vm::cancelEndEverySession) { Text("Отмена") } },
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

            // The door is drawn from the role the server read off this account's own row. It is the
            // only place in the client that mentions the queue, and it opens nothing by itself: the
            // three moderation routes answer 403 to any session whose row lacks the flag, so an entry
            // reached by other means — a restored back stack, a hand-built route — meets a refusal
            // rather than a list.
            if (state.isModerator) {
                Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                    SectionHeader("Модерация")
                    AppButton(
                        text = "Очередь жалоб",
                        onClick = onOpenModeration,
                        variant = AppButtonVariant.Tonal,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("Кого вы заблокировали")
                // The block list is the account's own, and it arrives or it does not. While the read
                // is out the rows are placeholders; a list that never answered says so with a retry
                // rather than showing «никого» — an empty profile and an unreadable one are different
                // answers, and here the second one is a privacy question.
                if (!state.blocksLoaded && !state.blocksUnknown) {
                    SkeletonBlock(modifier = Modifier.fillMaxWidth().height(72.dp))
                }
                if (state.blocksUnknown) {
                    InlineNotice(
                        "Не удалось проверить, кого вы заблокировали.",
                        actionLabel = "Повторить",
                        onAction = vm::loadBlocks,
                    )
                }
                if (state.blocksLoaded && state.blocked.isEmpty()) {
                    Text(
                        "Вы пока никого не блокировали.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                state.blocked.forEach { user ->
                    AppCard(modifier = Modifier.fillMaxWidth()) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(Spacing.lg),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(Spacing.md),
                        ) {
                            Avatar(url = user.photoUrl, size = 44.dp, initials = user.name)
                            Column(
                                modifier = Modifier.weight(1f),
                                verticalArrangement = Arrangement.spacedBy(2.dp),
                            ) {
                                Text(user.name, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
                                Text(
                                    blockedRowWord(user),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                            TextButton(
                                onClick = { vm.askUnblock(user) },
                                enabled = !state.blocksBusy,
                                // The name sits in the sibling column, so the tap alone would read
                                // as «Разблокировать» with nobody to unblock.
                                modifier = Modifier.semantics { contentDescription = "Разблокировать ${user.name}" },
                            ) {
                                Text("Разблокировать")
                            }
                        }
                    }
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("Устройства")
                // Every sign-in leaves a row behind, and this is the only place the account can read
                // them. The three states are drawn apart on purpose: a list that answered «no devices»
                // and a list that never answered are different answers, and on this section the second
                // one is a question about somebody else holding the account.
                if (!state.sessionsLoaded && !state.sessionsUnknown) {
                    SkeletonBlock(modifier = Modifier.fillMaxWidth().height(72.dp))
                }
                if (state.sessionsUnknown) {
                    InlineNotice(
                        "Не удалось проверить, на каких устройствах вы входите.",
                        actionLabel = "Повторить",
                        onAction = vm::loadSessions,
                    )
                }
                if (state.sessionsLoaded && state.sessions.isEmpty()) {
                    Text(
                        "Живых сеансов нет — аккаунт ни на одном устройстве не входит.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                state.sessions.forEach { session ->
                    AppCard(modifier = Modifier.fillMaxWidth()) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(Spacing.lg),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(Spacing.md),
                        ) {
                            SectionIcon(Icons.Outlined.PhoneAndroid, MaterialTheme.colorScheme.onSurfaceVariant)
                            Column(
                                modifier = Modifier.weight(1f),
                                verticalArrangement = Arrangement.spacedBy(2.dp),
                            ) {
                                Text(
                                    deviceWord(session),
                                    style = MaterialTheme.typography.bodyLarge,
                                    fontWeight = FontWeight.SemiBold,
                                )
                                val line = sessionRowWord(session)
                                if (line != null) {
                                    Text(
                                        line,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            }
                            TextButton(
                                onClick = { vm.askEndSession(session) },
                                enabled = !state.sessionsBusy,
                                // The device's own text sits in the sibling column, so TalkBack would
                                // otherwise announce a cut with nothing named.
                                modifier = Modifier.semantics {
                                    contentDescription = "Завершить сессию: ${deviceWord(session)}"
                                },
                            ) {
                                Text("Завершить")
                            }
                        }
                    }
                }
                if (state.sessionsTruncated) {
                    Text(
                        "Показаны самые свежие входы, и на этом список обрывается. Остальные завершает " +
                            "жест ниже.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (state.sessionsLoaded && state.sessions.isNotEmpty()) {
                    AppButton(
                        text = "Завершить все сессии",
                        onClick = vm::askEndEverySession,
                        variant = AppButtonVariant.Ghost,
                        contentColorOverride = MaterialTheme.colorScheme.error,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }

            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("Аккаунт")
                AppButton(
                    text = "Сменить пароль",
                    onClick = vm::askPasswordChange,
                    variant = AppButtonVariant.Tonal,
                    leadingIcon = Icons.Outlined.Lock,
                    modifier = Modifier.fillMaxWidth(),
                )
                if (state.passwordEditorOpen) {
                    AppCard(modifier = Modifier.fillMaxWidth()) {
                        PasswordEditor(
                            state = state,
                            onCancel = vm::cancelPasswordChange,
                            onSubmit = vm::submitPasswordChange,
                            onOldChange = vm::onPasswordOldChange,
                            onNewChange = vm::onPasswordNewChange,
                            onConfirmChange = vm::onPasswordConfirmChange,
                        )
                    }
                }
                AppButton(
                    text = "Выйти из аккаунта",
                    onClick = vm::logout,
                    variant = AppButtonVariant.Tonal,
                    leadingIcon = Icons.AutoMirrored.Outlined.Logout,
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

/**
 * The three words the account's own door asks for, in the order the server asks them.
 *
 * The old word comes first because a refusal must not cost the person a half-written password: the
 * server checks the new word's shape before it touches the old one, and neither the hash nor the live
 * sessions move when either question is answered wrong. The confirmation field is here for the same
 * reason register has it — the word is written once, and there is no second copy to read back from.
 */
@Composable
private fun PasswordEditor(
    state: SettingsUiState,
    onCancel: () -> Unit,
    onSubmit: () -> Unit,
    onOldChange: (String) -> Unit,
    onNewChange: (String) -> Unit,
    onConfirmChange: (String) -> Unit,
) {
    Column(
        modifier = Modifier.fillMaxWidth().padding(Spacing.lg),
        verticalArrangement = Arrangement.spacedBy(Spacing.md),
    ) {
        Text(
            "Новый пароль нужно ввести дважды. После смены ни одно устройство не останется в сессии, " +
                "включая это, — войти придётся заново.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        AppTextField(
            value = state.passwordOld,
            onValueChange = onOldChange,
            label = "Текущий пароль",
            isPassword = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
            modifier = Modifier.fillMaxWidth(),
        )
        AppTextField(
            value = state.passwordNew,
            onValueChange = onNewChange,
            label = "Новый пароль",
            isPassword = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
            modifier = Modifier.fillMaxWidth(),
        )
        AppTextField(
            value = state.passwordConfirm,
            onValueChange = onConfirmChange,
            label = "Повторите новый пароль",
            isPassword = true,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            onImeAction = onSubmit,
            modifier = Modifier.fillMaxWidth(),
        )
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.md),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            AppButton(
                text = "Сменить пароль",
                onClick = onSubmit,
                enabled = !state.busy,
                loading = state.busy,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = onCancel) { Text("Отмена") }
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

/**
 * The row's second line: who this person is to the account and when the block was written.
 *
 * The day comes off the server's own moment and is dropped rather than guessed when that text cannot
 * be read as one — a list about whom the account hides has no business inventing a date for it.
 */
internal fun blockedRowWord(user: BlockedUser, zone: ZoneId = ZoneId.systemDefault()): String {
    val identity = "${user.age} · ${user.city}"
    val day = runCatching {
        OffsetDateTime.parse(user.blockedAt)
            .atZoneSameInstant(zone)
            .format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale("ru")))
    }.getOrNull() ?: return identity
    return "$identity · $day"
}

/**
 * The session row's second line: which day the entry was made, which day the account stops being able
 * to renew it, and whether this is the row the person is reading the list from.
 *
 * Both moments come off the server's own text and are dropped when it cannot be read as one. The line
 * returns null when there is nothing to say — a row drawn with an invented date would be the screen
 * making up part of the evidence it is asking permission to act on.
 */
internal fun sessionRowWord(session: DeviceSession, zone: ZoneId = ZoneId.systemDefault()): String? {
    val parts = buildList {
        if (session.current) add("это устройство")
        dayWord(session.signedInAt, zone)?.let { add("вход $it") }
        dayWord(session.expiresAt, zone)?.let { add("до $it") }
    }
    return parts.joinToString(" · ").ifEmpty { null }
}

private fun dayWord(instant: String, zone: ZoneId): String? = runCatching {
    OffsetDateTime.parse(instant)
        .atZoneSameInstant(zone)
        .format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale("ru")))
}.getOrNull()
