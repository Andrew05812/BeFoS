package app.befos.presentation.settings

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
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
import androidx.compose.material.icons.outlined.Download
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
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
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
import app.befos.core.designsystem.ErrorRed
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.SkeletonBlock
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.rememberHaptics
import app.befos.core.designsystem.tabularDigits
import app.befos.domain.model.AccountExport
import app.befos.domain.model.BlockedUser
import app.befos.domain.model.DeviceSession
import app.befos.core.di.beFosViewModel
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun SettingsScreen(onBack: () -> Unit, onLoggedOut: () -> Unit, onOpenModeration: () -> Unit) {
    val vm: SettingsViewModel = beFosViewModel { SettingsViewModel(it.safetyRepository, it.authRepository, it.profileRepository) }
    val state by vm.uiState.collectAsState()
    val context = LocalContext.current
    val haptics = rememberHaptics()
    val writeScope = rememberCoroutineScope()
    // The callback below outlives the frame that registered it, so it reads the file the screen is
    // holding at the moment the system hands the uri back rather than the one it was built with.
    val heldExport by rememberUpdatedState(state.exported)

    // The system's own document provider: it asks for no storage permission, the person names the place,
    // and the app is handed one writable uri instead of a directory it could walk. Nothing is written
    // when the dialog comes back empty — that is a change of mind, and the file stays where it is.
    val saveExport = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/json")) { uri ->
        val file = heldExport
        if (uri != null && file != null) {
            writeScope.launch {
                // Megabytes of somebody's life leave through a stream the system may refuse; the write
                // belongs off the frame, and its failure belongs to the card that promised the file.
                val written = withContext(Dispatchers.IO) {
                    runCatching {
                        context.contentResolver.openOutputStream(uri)?.use { stream -> stream.write(file.bytes) } != null
                    }.getOrDefault(false)
                }
                if (written) {
                    haptics.success()
                    vm.markExportSaved()
                } else {
                    vm.markExportSaveFailed()
                }
            }
        }
    }

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

            Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                SectionHeader("Свои данные")
                // The door in front of the one below it. Everything the erasure takes is read back here
                // as one file, so «Удалить аккаунт» stops being the only way out and becomes a choice a
                // person can make after they have taken their own rows with them.
                AppCard(modifier = Modifier.fillMaxWidth()) {
                    Column(
                        modifier = Modifier.fillMaxWidth().padding(Spacing.xl),
                        verticalArrangement = Arrangement.spacedBy(Spacing.md),
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(Spacing.md),
                        ) {
                            SectionIcon(Icons.Outlined.Download, MaterialTheme.colorScheme.onSurfaceVariant)
                            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text("Выгрузить мои данные", style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
                                Text(
                                    "Один файл со всем, что аккаунт написал сам: анкета, снимки, касания, " +
                                        "пары, переписка, планы, жалобы и устройства, которые входят в аккаунт.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                        AppButton(
                            text = if (state.exportBusy) "Собираем ваши строки…" else "Выгрузить",
                            onClick = vm::exportAccount,
                            variant = AppButtonVariant.Tonal,
                            enabled = !state.exportBusy,
                            loading = state.exportBusy,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
                // A download is the one read on this screen that is not started by opening it, so the
                // empty placeholder is drawn only while the person is waiting on their own tap.
                if (state.exportBusy) {
                    SkeletonBlock(modifier = Modifier.fillMaxWidth().height(96.dp))
                }
                if (state.exportUnknown) {
                    InlineNotice(
                        "Не удалось выгрузить ваши данные.",
                        actionLabel = "Повторить",
                        onAction = vm::exportAccount,
                    )
                }
                state.exported?.let { file ->
                    AppCard(modifier = Modifier.fillMaxWidth()) {
                        Column(
                            modifier = Modifier.fillMaxWidth().padding(Spacing.xl),
                            verticalArrangement = Arrangement.spacedBy(Spacing.md),
                        ) {
                            Text(
                                if (file.isFreshAccount) "Файл готов: в нём пока только анкета" else "Файл готов",
                                style = MaterialTheme.typography.bodyLarge,
                                fontWeight = FontWeight.SemiBold,
                            )
                            // Label before number, everywhere: the counts have no plural table here, and
                            // an invented one would be a second copy of the grammar the file is written in.
                            ExportLine("Записей в файле", file.totalRows.toString())
                            ExportLine("Размер", exportSizeWord(file.sizeBytes))
                            exportDayWord(file.generatedAt)?.let { day -> ExportLine("Создан", day) }
                            // Only the sections that hold something: a card that lists thirteen zeros says
                            // the account was read, and hides which parts of it are actually there.
                            val filled = file.sections.filter { it.rows > 0 }
                            if (filled.isNotEmpty()) {
                                Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                                    filled.forEach { section ->
                                        ExportLine(exportSectionWord(section.name), section.rows.toString())
                                    }
                                }
                            }
                            exportCutsWord(file)?.let { cuts ->
                                // The ceiling is the server's, and the card repeats it: a file that holds
                                // part of a list must not be drawn as the whole of one.
                                InlineNotice("Не всё поместилось в файл: $cuts.", isError = false)
                            }
                            if (state.exportSaved) {
                                InlineNotice(
                                    "Сохранено на устройстве: ${file.fileName}",
                                    isError = false,
                                    modifier = Modifier.semantics { contentDescription = "Файл сохранён: ${file.fileName}" },
                                )
                            }
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(Spacing.md),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                AppButton(
                                    text = "Сохранить файл",
                                    onClick = { saveExport.launch(file.fileName) },
                                    // The door stays open after one write: nothing about saving the same
                                    // rows to a second place is unsafe, and closing it would be the screen
                                    // claiming it knows where the person wanted the file.
                                    modifier = Modifier.weight(1f),
                                )
                                TextButton(
                                    onClick = vm::discardExport,
                                    modifier = Modifier.semantics { contentDescription = "Убрать выгрузку" },
                                ) {
                                    Text("Убрать")
                                }
                            }
                        }
                    }
                }
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
                            // The pointer is the part this screen could not make until the door above it
                            // existed. The erasure stays exactly as harsh as it was; what changed is that
                            // a person standing in front of it now has a way to take their own rows first.
                            Text(
                                "Свои строки можно вынести заранее — в разделе «Свои данные» выше.",
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

/**
 * One line of the finished file's card: what the document calls the section, and how many rows of it
 * the file carries.
 *
 * The label sits on the weight and the number on the end, so a name that grows with the text scale
 * takes room from the label rather than pushing the digits off the row.
 */
@Composable
private fun ExportLine(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(Spacing.md),
        verticalAlignment = Alignment.Top,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f),
        )
        Text(value, style = MaterialTheme.typography.labelLarge.tabularDigits())
    }
}

/**
 * How big the file is, in whole units rounded down.
 *
 * Three words rather than a byte count: a person comparing the card with the file they saved has to be
 * able to say which is which, and a card that rounded 2,5 КБ up to 3 would be describing bytes that did
 * not arrive.
 */
internal fun exportSizeWord(bytes: Int): String {
    val kib = 1024L
    val mib = kib * kib
    val value = bytes.toLong()
    return when {
        value < kib -> "$bytes Б"
        value < mib -> "${value / kib} КБ"
        else -> {
            val tenths = value * 10 / mib
            "${tenths / 10},${tenths % 10} МБ"
        }
    }
}

/**
 * The section's name in the screen's own words, and the document's key when the screen has no word.
 *
 * The fallback is deliberate: a key this build never saw is the server's own name for a section, and a
 * person can find it in the file by that spelling. An invented translation would be a label pointing at
 * nothing.
 */
internal fun exportSectionWord(name: String): String = when (name) {
    "photos" -> "снимки"
    "questionnaire_answers" -> "ответы анкеты"
    "questionnaire_categories" -> "разделы анкеты"
    "taps_given" -> "ваши касания"
    "taps_received" -> "касания вам"
    "taps_passed" -> "пропуски"
    "deck" -> "колода"
    "pairs" -> "пары"
    "chats" -> "переписка"
    "plans" -> "планы"
    "blocks" -> "заблокированные"
    "complaints" -> "жалобы"
    "sessions" -> "устройства"
    else -> name
}

/**
 * Which parts of the file the server cut short, in one sentence — or nothing, when the ceiling was
 * never reached. The card cannot present a part of a list as the whole of one, and it cannot say so
 * from arithmetic either: the document names its own cuts.
 */
internal fun exportCutsWord(export: AccountExport): String? =
    export.truncated.joinToString(", ") { exportSectionWord(it) }.ifEmpty { null }

/** The day the file was written, in the reader's own zone, or nothing the client has to invent. */
internal fun exportDayWord(generatedAt: String, zone: ZoneId = ZoneId.systemDefault()): String? =
    dayWord(generatedAt, zone)

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
