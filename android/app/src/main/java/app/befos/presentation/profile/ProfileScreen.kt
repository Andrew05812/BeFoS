package app.befos.presentation.profile

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.outlined.AddAPhoto
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.StarBorder
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.Avatar
import app.befos.core.designsystem.EmberGradient
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.IrisSoft
import app.befos.core.designsystem.ProfileSkeleton
import app.befos.core.designsystem.RemotePhoto
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.answersWord
import app.befos.core.designsystem.rememberHaptics
import app.befos.core.designsystem.tabularDigits
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.ProfilePhoto
import app.befos.presentation.common.goalLabel
import app.befos.presentation.common.myProfileEntryWord
import java.io.FileNotFoundException

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ProfileScreen(
    onEdit: () -> Unit,
    onSettings: () -> Unit,
    onTest: () -> Unit,
    onOpenMyProfile: () -> Unit,
    onLoggedOut: () -> Unit,
) {
    val vm: ProfileViewModel = beFosViewModel {
        ProfileViewModel(it.profileRepository, it.testRepository, it.authRepository)
    }
    val state by vm.uiState.collectAsState()
    val context = LocalContext.current
    val haptics = rememberHaptics()
    // The system's own picture chooser: it needs no permission of ours, and it hands back one
    // readable uri rather than a directory the app would have to be allowed to walk.
    val pickPhoto = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        // Nothing back is a change of mind, not a failure, so the screen keeps its silence.
        if (uri != null) {
            val resolver = context.contentResolver
            // The tick belongs to the moment the picture leaves the device, not to the tap that
            // opened the chooser: a person who backed out of the picker gets nothing promised.
            haptics.medium()
            vm.uploadPhoto(resolver.getType(uri)) {
                resolver.openInputStream(uri)
                    ?: throw FileNotFoundException("the picker handed back a uri it would not open")
            }
        }
    }

    LaunchedEffect(state.loggedOut) { if (state.loggedOut) onLoggedOut() }

    LifecycleResumeEffect(Unit) {
        vm.refreshSilently()
        onPauseOrDispose { }
    }

    when {
        state.loading -> ProfileSkeleton()
        state.profile == null -> ErrorState(
            message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
            title = "Не удалось загрузить профиль",
            onRetry = vm::load,
        )
        else -> {
            val profile = state.profile!!
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .padding(start = Spacing.gutter, top = Spacing.xl, end = Spacing.gutter, bottom = 96.dp),
                verticalArrangement = Arrangement.spacedBy(Spacing.xxl),
            ) {
                state.refreshError?.let {
                    InlineNotice(it, actionLabel = "Повторить", onAction = vm::refreshSilently)
                }
                ProfileHero(profile.primaryPhoto, "${profile.name}, ${profile.age}", profile.city, goalLabel(profile.datingGoal))

                PhotoSection(
                    photos = profile.photos,
                    uploading = state.uploading,
                    busy = state.photoBusy,
                    uploadError = state.uploadError,
                    photoError = state.photoError,
                    pendingDeletion = state.pendingDeletion,
                    onPick = {
                        pickPhoto.launch(
                            PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly),
                        )
                    },
                    onRefresh = vm::refreshSilently,
                    onMove = vm::movePhoto,
                    onMakePrimary = vm::makePhotoPrimary,
                    onAskDelete = vm::askDeletePhoto,
                    onCancelDelete = vm::cancelDeletePhoto,
                    onConfirmDelete = vm::confirmDeletePhoto,
                )

                if (!profile.about.isNullOrBlank()) {
                    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                        SectionHeader("О себе")
                        Text(profile.about, style = MaterialTheme.typography.bodyLarge)
                    }
                }

                TestProgressCard(
                    percent = state.testProgress?.percent ?: 0,
                    answered = state.testProgress?.answered ?: 0,
                    total = state.testProgress?.total ?: 0,
                    completed = state.testProgress?.completed ?: false,
                    failed = state.testProgress == null && state.testProgressFailed,
                    onTest = onTest,
                    onOpenMyProfile = onOpenMyProfile,
                )

                if (profile.interests.isNotEmpty()) {
                    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
                        SectionHeader("Интересы")
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                        ) {
                            profile.interests.forEach { interest ->
                                InterestChip(label = interest.name)
                            }
                        }
                    }
                }

                // Full width: side by side "Редактировать" broke mid-word on a 320dp
                // screen, and the two actions are not a pair the user compares.
                Column(
                    modifier = Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(Spacing.md),
                ) {
                    AppButton(
                        text = "Редактировать анкету",
                        onClick = onEdit,
                        leadingIcon = Icons.Filled.Edit,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    AppButton(
                        text = "Настройки",
                        onClick = onSettings,
                        variant = AppButtonVariant.Tonal,
                        leadingIcon = Icons.Outlined.Settings,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
    }
}

/** Branded identity panel: photo/initial on a warm gradient, name front and center. */
@Composable
private fun ProfileHero(photoUrl: String?, title: String, city: String, goal: String) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.large)
            .background(Brush.verticalGradient(listOf(IrisSoft, MaterialTheme.colorScheme.surface)))
            .border(1.dp, MaterialTheme.colorScheme.outlineVariant, MaterialTheme.shapes.large),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(Spacing.xxl),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            Text(
                "МОЙ ПРОФИЛЬ",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(Spacing.lg),
            ) {
                Avatar(photoUrl, size = 76.dp, initials = title, contentDescription = title)
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                    // A profile that never answered the city question reaches this screen
                    // when the root gate times out; an empty row here would be a gap in
                    // the hero with nothing to explain it.
                    if (city.isNotBlank()) {
                        Text(city, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    // The hero panel fades from iris-soft, which is lighter than paper, so
                    // the fill ember here would read below 4.5:1 at labelLarge.
                    Text(goal, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onPrimaryContainer)
                }
            }
        }
    }
}

/**
 * The photographs the server holds for this person, in the order it sent them, and the four things
 * the owner can do to that row: add one, lead with one, move one, remove one.
 *
 * Everything painted here came back from the server — `POST /users/me/photo`, `GET /users/me`, or the
 * answer to one of the three management writes. The bytes the picker handed over are never shown as a
 * preview, because the route re-encodes the file and keeps the copy, so a preview would promise a
 * picture the pair may never be shown.
 *
 * A row rather than a strip of tiles: every control needs a real touch target, and four of them side
 * by side do not fit over a 104dp tile on the narrowest screen this app is checked on. Read
 * top-down, the list is also the order — the first row is the photograph the deck opens with.
 */
@Composable
private fun PhotoSection(
    photos: List<ProfilePhoto>,
    uploading: Boolean,
    busy: Boolean,
    uploadError: String?,
    photoError: String?,
    pendingDeletion: String?,
    onPick: () -> Unit,
    onRefresh: () -> Unit,
    onMove: (String, Int) -> Unit,
    onMakePrimary: (String) -> Unit,
    onAskDelete: (String) -> Unit,
    onCancelDelete: () -> Unit,
    onConfirmDelete: () -> Unit,
) {
    // One gate for every control: two writes to the same row cannot travel together, and the answer
    // that comes back is the row the server now holds — so nothing else may be started until it lands.
    val settled = !uploading && !busy
    val pendingIndex = pendingDeletion?.let { id -> photos.indexOfFirst { it.id == id } } ?: -1
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
        SectionHeader("Фото")
        uploadError?.let { InlineNotice(it, actionLabel = "Выбрать заново", onAction = onPick) }
        photoError?.let {
            // The row on screen is the row the server still holds. «Обновить» reads that row back,
            // so a refusal that came from a stale screen is settled by the same tap that answers it.
            InlineNotice(it, actionLabel = "Обновить", onAction = onRefresh)
        }
        if (photos.isEmpty()) {
            // The deck a person is swiped through carries no face until this row is filled, so
            // the empty state says what is missing rather than only offering a button.
            Text(
                text = if (uploading) "Отправляем первое фото." else "Фото пока нет — подбор показывает вас без снимка.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                photos.forEachIndexed { index, photo ->
                    PhotoRow(
                        photo = photo,
                        position = index,
                        total = photos.size,
                        enabled = settled,
                        onMove = { delta -> onMove(photo.id, delta) },
                        onMakePrimary = { onMakePrimary(photo.id) },
                        onAskDelete = { onAskDelete(photo.id) },
                    )
                }
            }
            if (photos.size > 1) {
                Text(
                    "Первый снимок — главный: его видит подбор и анкета, которую открыла пара.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        AppButton(
            text = "Загрузить фото",
            onClick = onPick,
            loading = uploading,
            enabled = settled,
            variant = AppButtonVariant.Tonal,
            leadingIcon = Icons.Outlined.AddAPhoto,
            modifier = Modifier.fillMaxWidth(),
        )
    }
    // Shown only while the asked-about photograph is still on the row: a background read that
    // removed it underneath the question has already answered the question.
    if (pendingIndex >= 0) {
        DeletePhotoDialog(
            position = pendingIndex,
            total = photos.size,
            onConfirm = onConfirmDelete,
            onDismiss = onCancelDelete,
        )
    }
}

/**
 * One photograph, the place it holds in the row, and what the owner may do to it.
 *
 * A control that cannot apply to this row stays visible and disabled rather than vanishing: the row
 * keeps its width as the person scrolls, and a button that is dimmed says the action exists and is
 * simply not available here (nothing moves above the first row, nothing leads with the last).
 */
@Composable
private fun PhotoRow(
    photo: ProfilePhoto,
    position: Int,
    total: Int,
    enabled: Boolean,
    onMove: (Int) -> Unit,
    onMakePrimary: () -> Unit,
    onAskDelete: () -> Unit,
) {
    val isFirst = position == 0
    val isLast = position == total - 1
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(Spacing.xs),
        ) {
            Box(
                modifier = Modifier
                    .size(width = 64.dp, height = 80.dp)
                    .clip(MaterialTheme.shapes.medium)
                    .background(EmberGradient),
            ) {
                RemotePhoto(
                    url = photo.url,
                    contentDescription = "Снимок ${position + 1} из $total",
                    modifier = Modifier.matchParentSize(),
                )
            }
            Text(
                text = if (isFirst) "Главная" else "Снимок ${position + 1}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Spacer(Modifier.weight(1f))
        IconButton(onClick = onMakePrimary, enabled = !isFirst && enabled) {
            Icon(
                imageVector = if (isFirst) Icons.Filled.Star else Icons.Outlined.StarBorder,
                contentDescription = if (isFirst) "Это главный снимок" else "Сделать главным",
            )
        }
        IconButton(onClick = { onMove(-1) }, enabled = !isFirst && enabled) {
            Icon(Icons.Filled.KeyboardArrowUp, contentDescription = "Переставить выше")
        }
        IconButton(onClick = { onMove(1) }, enabled = !isLast && enabled) {
            Icon(Icons.Filled.KeyboardArrowDown, contentDescription = "Переставить ниже")
        }
        // Any row can go, including the only one: an empty photograph row is a state the server
        // holds and the screens already paint («подбор показывает вас без снимка»).
        IconButton(onClick = onAskDelete, enabled = enabled) {
            Icon(Icons.Outlined.Delete, contentDescription = "Удалить снимок")
        }
    }
}

/**
 * Removal asks first, in the same two-step the account deletion and the block use. The route deletes
 * the stored file, and nothing in the app puts a removed photograph back — the dialog is the only
 * place a mistaken tap can still be stopped, so it names what this particular removal costs.
 */
@Composable
private fun DeletePhotoDialog(
    position: Int,
    total: Int,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Удалить фото?") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                Text(
                    when {
                        total == 1 -> "Это единственный снимок — анкета останется без фото, и подбор покажет вас без него."
                        position == 0 -> "Это главный снимок. Главным станет следующий по порядку."
                        else -> "Снимок ${position + 1} исчезнет из подборки и из анкеты, которую видят другие."
                    },
                )
                Text(
                    "Отменить удаление нельзя — фото придётся загружать заново.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            TextButton(onClick = onConfirm) {
                Text("Удалить", color = MaterialTheme.colorScheme.error)
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } },
    )
}

@Composable
private fun TestProgressCard(
    percent: Int,
    answered: Int,
    total: Int,
    completed: Boolean,
    failed: Boolean,
    onTest: () -> Unit,
    onOpenMyProfile: () -> Unit,
) {
    val lines = testProgressCopy(answered = answered, total = total, completed = completed, failed = failed)
    var visible by remember { androidx.compose.runtime.mutableStateOf(false) }
    LaunchedEffect(Unit) { visible = true }
    val fill by animateFloatAsState(
        targetValue = if (visible && !failed) percent / 100f else 0f,
        animationSpec = tween(Motion.Slow, easing = androidx.compose.animation.core.FastOutSlowInEasing),
        label = "testProgressFill",
    )
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                    Text("ТЕСТ СОВМЕСТИМОСТИ", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(
                        lines.title,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                // The bare number used to sit under "Профиль совместимости" and read as a
                // compatibility score of 100%. It is answer coverage — so it says so.
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        if (failed) "—" else "$percent%",
                        style = MaterialTheme.typography.headlineSmall.tabularDigits(),
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        "отвечено",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(10.dp)
                    .clip(RoundedCornerShape(5.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant),
            ) {
                Box(
                    Modifier
                        .fillMaxWidth(fill)
                        .height(10.dp)
                        .clip(RoundedCornerShape(5.dp))
                        .background(EmberGradient),
                )
            }
            Text(
                lines.body,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            AppButton(
                text = lines.button,
                onClick = onTest,
                variant = if (completed) AppButtonVariant.Tonal else AppButtonVariant.Filled,
                modifier = Modifier.fillMaxWidth(),
            )
            // The reading the questionnaire produced is the person's to keep, not the evening's:
            // engine rebuilds the profile on every saved answer, so once one card is answered there
            // is a profile to open. Offered as a question, not as a percent — this card already
            // spends its number on coverage, and a second number here would read as a score.
            if (myProfileEntryVisible(answered, failed)) {
                TextButton(
                    onClick = onOpenMyProfile,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(myProfileEntryWord())
                }
            }
        }
    }
}

/** Whether there is a stored profile this card can honestly offer to open. */
internal fun myProfileEntryVisible(answered: Int, failed: Boolean): Boolean =
    !failed && answered > 0

/** Three lines the test card prints, one per state the person can be in. */
internal data class TestProgressCopy(val title: String, val body: String, val button: String)

/**
 * Answers on the server are a different case from no answers: the test screen opens on the first
 * unmarked question, so the entry point has to offer what it actually leads to. The counts quoted
 * here are the ones `/tests/progress` returned — the card does not count anything itself.
 */
internal fun testProgressCopy(answered: Int, total: Int, completed: Boolean, failed: Boolean): TestProgressCopy =
    when {
        failed -> TestProgressCopy(
            title = "Прогресс теста не загрузился",
            body = "Данные теста не загрузились — попробуйте обновить.",
            button = "Пройти тест",
        )
        completed -> TestProgressCopy(
            title = "Тест пройден",
            body = "Вы можете пройти тест заново, чтобы уточнить ответы.",
            button = "Пройти заново",
        )
        answered > 0 -> TestProgressCopy(
            title = "Тест начат",
            body = "На сервере ${answered} ${answersWord(answered)} из ${total} — " +
                "откроется с вопроса, где вы остановились.",
            button = "Продолжить тест",
        )
        else -> TestProgressCopy(
            title = "Тест не пройден",
            body = "Пройдите тест — без него совместимость считается неточно.",
            button = "Пройти тест",
        )
    }
