package app.befos.presentation.plans

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.ChoiceChip
import app.befos.core.designsystem.Elev
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.ListSkeleton
import app.befos.core.designsystem.Spacing
import app.befos.core.di.beFosViewModel
import app.befos.core.notifications.PlanReminders
import app.befos.domain.model.Plan
import app.befos.domain.model.PlanDecisions
import app.befos.domain.model.PlanStatuses
import app.befos.presentation.recommendations.formatMeetingInstant
import app.befos.presentation.recommendations.meetingDayLabel
import app.befos.presentation.recommendations.meetingDays
import app.befos.presentation.recommendations.meetingHourLabel
import app.befos.presentation.recommendations.meetingHours
import app.befos.presentation.recommendations.meetingInstant
import app.befos.presentation.recommendations.offerButtonLabel
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime

/**
 * The pair's plans, read from the server's plan rows.
 *
 * Every fact here comes from one read of the pair's list and is asked back again after every write
 * that landed: a plan is one entity shared by the chat, the journal and the idea card, and a screen
 * that kept its own answer of it would be a second copy the other half's taps never touched. Whose
 * plan this is does not travel in the route either — the session answers that, and the server reads
 * the person's own half from it.
 */
@Composable
fun PlansScreen(
    matchId: String,
    focusPlanId: String?,
    onBack: () -> Unit,
    onOpenHistory: (String) -> Unit,
) {
    val vm: PlansViewModel =
        beFosViewModel { PlansViewModel(it.planRepository, it.chatRepository, matchId) }
    val state by vm.uiState.collectAsState()
    val sections = remember(state.plans) { planSections(state.plans) }
    val listState = rememberLazyListState()
    val context = LocalContext.current
    // The clock is read once for the visit, not once per recomposition: a card whose hour row
    // recomputed itself mid-glance could drop a chip under the finger already aiming at it. The same
    // single reading is what the alarms below are set against, so a card and its reminder cannot
    // disagree about whether the hour is still ahead.
    val now = remember { ZonedDateTime.now() }
    // Whether a notice this app posts can reach the person is the device's answer, not this copy's, so
    // it is re-read from the system: on the visit, after every re-read of the list, and after the
    // permission screen hands its result back.
    var canPost by remember { mutableStateOf(PlanReminders.canPost(context)) }
    val askToPost = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        canPost = PlanReminders.canPost(context)
    }
    // An hour both halves stand on is a plan this device has promised to call. A page that holds one
    // and cannot say it out loud names the missing permission rather than letting the person assume
    // the reminder is set; a page with no hour to call has nothing to apologise for.
    val reminderBlocked = !canPost && state.plans.any { reminderFor(it, now) != null }
    // A refused refresh that leaves the cards standing costs its own row over the list, so the row a
    // tap from the chat leads to is counted from the same flags the list reads.
    val headerRows = 1 +
        (if (state.error != null) 1 else 0) +
        (if (state.outdated != null) 1 else 0) +
        (if (reminderBlocked) 1 else 0)
    val focusRow = focusPlanId?.let { planFocusRow(it, sections, headerRows) }
    LaunchedEffect(focusRow, state.loading) {
        if (!state.loading && focusRow != null) listState.scrollToItem(focusRow)
    }
    // The pair's hours are put on the device's clock whenever this page reads them: a moved hour
    // replaces its own alarm, and a plan that stopped being an agreement loses it. This is the whole
    // delivery — the app holds no key for a messaging service and the reminder comes from this phone.
    LaunchedEffect(state.plans) {
        PlanReminders.sync(context, state.plans, now)
        canPost = PlanReminders.canPost(context)
    }

    Scaffold(
        topBar = { AppTopBar(title = "Наши планы", onBack = onBack) },
    ) { padding ->
        when {
            state.loading -> ListSkeleton(Modifier.padding(padding), rows = 4)
            state.error != null && state.plans.isEmpty() -> ErrorState(
                message = state.error.orEmpty(),
                title = "Не удалось загрузить планы",
                onRetry = vm::load,
                modifier = Modifier.padding(padding),
            )
            state.outdated != null && state.plans.isEmpty() -> ErrorState(
                // The pair's thread said a plan moved while this page held no rows to keep. «Планов
                // пока нет» would then be a sentence the socket has already contradicted, so the page
                // says the one thing it knows: the arrangement moved and this copy did not read it.
                message = state.outdated.orEmpty(),
                title = "План пары изменился",
                onRetry = vm::load,
                modifier = Modifier.padding(padding),
            )
            state.plans.isEmpty() -> EmptyState(
                title = "Планов пока нет",
                message = "Пара ещё не выбрала идею для встречи. Договоритесь в переписке или поддержите идею из подборки — план появится здесь.",
                overline = "Планы",
                actionLabel = "Обновить",
                onAction = vm::load,
                modifier = Modifier.padding(padding),
            )
            else -> LazyColumn(
                state = listState,
                modifier = Modifier.padding(padding).fillMaxSize().padding(horizontal = Spacing.gutter),
                verticalArrangement = Arrangement.spacedBy(Spacing.lg),
                contentPadding = PaddingValues(vertical = Spacing.lg),
            ) {
                if (state.error != null) {
                    item {
                        // The cards below are the last honest reading the pair has; this line says the
                        // page could not refresh them, and the retry is the same read the visit made.
                        InlineNotice(
                            text = state.error.orEmpty(),
                            actionLabel = "Повторить",
                            onAction = vm::load,
                        )
                    }
                }
                state.outdated?.let { word ->
                    item {
                        // The pair's socket said the arrangement moved and this page could not read the
                        // new one. The cards below stay, because they are what the pair last saw the
                        // server agree on — but they are named as that, rather than as the plan now.
                        InlineNotice(text = word, actionLabel = "Перечитать", onAction = vm::load)
                    }
                }
                if (reminderBlocked) {
                    item {
                        // Not an error: nothing failed. The row says what the device will not do until
                        // the person allows it, and the one tap that settles it is the system's own
                        // permission screen.
                        InlineNotice(
                            text = REMINDER_NEEDS_PERMISSION_WORD,
                            isError = false,
                            actionLabel = "Разрешить",
                            onAction = { askToPost.launch(Manifest.permission.POST_NOTIFICATIONS) },
                        )
                    }
                }
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                        Text(
                            "ПЛАН ПАРЫ",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Text(
                            "Здесь всё, о чём вы договариваетесь: идея, час, договорённость и отменённое. " +
                                "Обе половины отвечают на один и тот же план, а не на его копию.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        if (focusPlanId != null && focusRow == null) {
                            // The chat named a plan this page no longer holds — a pair dissolved, a
                            // row taken away. Saying so beats arriving at a card nobody asked about.
                            Text(
                                "План, о котором вы читали в переписке, больше не в этом списке.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
                sections.forEach { section ->
                    item {
                        Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                            Text(
                                section.title.uppercase(),
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.onSurface,
                            )
                            Text(
                                section.caption,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    items(section.plans, key = { it.id }) { plan ->
                        PlanCard(
                            plan = plan,
                            now = now,
                            busy = state.busy.contains(plan.id),
                            error = state.tapErrors[plan.id],
                            onAccept = { vm.accept(plan.id) },
                            onDecline = { vm.decline(plan.id) },
                            onRestoreDecline = { vm.restoreDecline(plan.id) },
                            onOfferHour = { whenIso -> vm.offerHour(plan.id, whenIso) },
                            onConfirmHour = { whenIso -> vm.confirmHour(plan.id, whenIso) },
                            onCancel = { vm.cancel(plan.id) },
                            onRestore = { vm.restore(plan.id) },
                            onMarkAttended = { vm.markAttended(plan.id) },
                            onUndoAttended = { vm.undoAttended(plan.id) },
                            onSaveWords = { place, note -> vm.saveWords(plan.id, place, note) },
                            onOpenHistory = { onOpenHistory(plan.id) },
                        )
                    }
                }
            }
        }
    }
}

/**
 * The row a named plan sits on, counted the way the list above is really built.
 *
 * Every section costs its own heading row plus one row per card, and a notice over the list shifts
 * all of them. A tap from the chat that scrolls to the wrong card is worse than one that does not
 * scroll, so the count is written out here — where the test beside it can read it. Null when the plan
 * is not on this page.
 */
internal fun planFocusRow(planId: String, sections: List<PlanSection>, headerRows: Int): Int? {
    var row = headerRows
    sections.forEach { section ->
        val at = section.plans.indexOfFirst { it.id == planId }
        if (at >= 0) return row + at
        row += 1 + section.plans.size
    }
    return null
}

@Composable
private fun PlanCard(
    plan: Plan,
    now: ZonedDateTime,
    busy: Boolean,
    error: String?,
    onAccept: () -> Unit,
    onDecline: () -> Unit,
    onRestoreDecline: () -> Unit,
    onOfferHour: (String) -> Unit,
    onConfirmHour: (String) -> Unit,
    onCancel: () -> Unit,
    onRestore: () -> Unit,
    onMarkAttended: () -> Unit,
    onUndoAttended: () -> Unit,
    onSaveWords: (String, String) -> Unit,
    onOpenHistory: () -> Unit,
) {
    val settled = plan.status == PlanStatuses.CANCELLED || plan.status == PlanStatuses.DECLINED
    // Whose hour the plan is waiting on, said once: the card shows it as an offer, the hour row names
    // its own button after it, and both readings have to agree about whose word is missing.
    val offeredByPartner = plan.partnerNamedTheHour
    val partnerOffer = if (offeredByPartner) plan.pendingHour else null
    val myOffer = if (offeredByPartner) null else plan.pendingHour
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(Spacing.xl),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    plan.title,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f, fill = false),
                )
                StatusBadge(
                    planStatusWord(plan),
                    if (settled) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.primary,
                )
            }
            if (!plan.description.isNullOrBlank()) {
                Text(
                    plan.description,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(
                plan.partnerName?.let { "Вы и $it" } ?: "Ваша пара",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            planHourWord(plan, now)?.let { hour ->
                val standing = planHourIsThePairWord(plan, now)
                ChoiceChip(
                    hour,
                    if (standing) Icons.Filled.CheckCircle else Icons.Filled.Schedule,
                    selected = standing,
                )
            }
            planAttendanceWord(plan)?.let { attendance ->
                ChoiceChip(attendance, Icons.Filled.CheckCircle, selected = true)
            }
            // An hour one half has named and the other has not answered is not the pair's plan, so it
            // is shown as an offer and never with the words the agreement is named by.
            if (partnerOffer != null) {
                ChoiceChip(
                    "Партнёр предлагает: ${formatMeetingInstant(partnerOffer, now, now.zone)}",
                    Icons.AutoMirrored.Filled.Send,
                )
                if (plan.needsMyAnswer) {
                    // The instant goes back exactly as this card read it: an hour the partner has
                    // moved in the meantime is refused rather than agreed to silently.
                    AppButton(
                        text = "Подходит",
                        onClick = { onConfirmHour(partnerOffer) },
                        enabled = !busy,
                        variant = AppButtonVariant.Tonal,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            } else if (myOffer != null) {
                ChoiceChip(
                    "Вы предложили: ${formatMeetingInstant(myOffer, now, now.zone)}",
                    Icons.Filled.Schedule,
                )
            }
            HourEditor(plan = plan, mine = myOffer, now = now, busy = busy, onOfferHour = onOfferHour)
            // This person's own answer, in the three doors it can be moved through: say yes, say no,
            // take the no back. The rule is read off whose word the row holds rather than off the
            // plan's status, because the two are different questions — a plan the partner has refused
            // is still waiting for this card's answer, and a plan this person has confirmed is still
            // theirs to refuse. Nothing here reaches the other half's answer: the server owns that door.
            when {
                !canAnswerPlan(plan) -> planAnswerWord(plan)?.let { closed ->
                    Text(
                        closed,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                plan.myDecision == PlanDecisions.DECLINED ->
                    QuietAction("Вернуть идею", busy, onRestoreDecline)
                plan.myDecision == PlanDecisions.JOINED ->
                    QuietAction("Отказаться", busy, onDecline)
                else -> {
                    AppButton(
                        text = "Поддержать идею",
                        onClick = onAccept,
                        enabled = !busy,
                        variant = AppButtonVariant.Tonal,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    QuietAction("Отклонить идею", busy, onDecline)
                }
            }
            if (canMarkAttended(plan)) {
                AppButton(
                    text = "Состоялось",
                    onClick = onMarkAttended,
                    enabled = !busy,
                    variant = AppButtonVariant.Tonal,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            if (plan.iAttended) QuietAction("Снять отметку", busy, onUndoAttended)
            // Calling the plan off is the one tap here that ends something the other half is reading as
            // standing, so the card asks before it writes. The dialog says what survives — the pair's
            // conversation, the plan's history, the hour the arrangement stood on — and whose word it
            // does not touch: the partner's own answer about the idea stays theirs.
            if (plan.canCancel) {
                var confirmingCancel by remember { mutableStateOf(false) }
                QuietAction("Отменить план", busy) { confirmingCancel = true }
                if (confirmingCancel) {
                    AlertDialog(
                        onDismissRequest = { confirmingCancel = false },
                        title = { Text("Отменить план «${plan.title}»?") },
                        text = {
                            Text(
                                "Отмена видна вам обоим: план перейдёт в «Отменено», а названный час " +
                                    "перестанет держаться. Переписка и история плана останутся, и " +
                                    "вернётся тот же час, если план вернуть. Ваш партнёр ничего не " +
                                    "отменяет — его ответ об идее остаётся его словом."
                            )
                        },
                        confirmButton = {
                            TextButton(
                                onClick = {
                                    confirmingCancel = false
                                    onCancel()
                                },
                            ) {
                                Text("Отменить план", color = MaterialTheme.colorScheme.error)
                            }
                        },
                        dismissButton = {
                            TextButton(onClick = { confirmingCancel = false }) { Text("Назад") }
                        },
                    )
                }
            }
            if (plan.status == PlanStatuses.CANCELLED) {
                AppButton(
                    text = "Вернуть план",
                    onClick = onRestore,
                    enabled = !busy,
                    variant = AppButtonVariant.Ghost,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            // The pair's own two words about the arrangement: where they meet, and what they said
            // about it. Something still ahead of the pair is edited here; a meeting that happened or
            // was called off keeps its words as history, printed rather than typed.
            if (canEditPlanWords(plan)) {
                WordsEditor(plan = plan, busy = busy, onSaveWords = onSaveWords)
            } else {
                plan.place?.takeIf { it.isNotBlank() }?.let { place ->
                    Text(
                        "Место: $place",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                plan.note?.takeIf { it.isNotBlank() }?.let { note ->
                    Text(
                        "Заметка пары: $note",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            // The plan's own chronology, openable from the card that holds it. This door is the one
            // the card never closes: a plan that was called off or lived through keeps every line
            // the pair wrote about it, and the record is the thing a person reaches for exactly when
            // the arrangement is no longer standing.
            QuietAction("Посмотреть историю изменений", busy = false) { onOpenHistory() }
            error?.let { InlineNotice(text = it) }
        }
    }
}

/**
 * The hour row, opened only for a plan this person may still move.
 *
 * Which evening to offer is a decision being made, not a fact about the pair, so it never enters the
 * view state — the card holds it until the tap that sends it. The row opens over a standing hour too:
 * an evening the pair has agreed on and not yet lived through is exactly the thing a person can be
 * asked to move, and the button names that act rather than leaving the row hidden until the hour has
 * been missed. The offers themselves close over a plan the pair still stands on and come back once
 * that hour is behind them, because the server refuses a moment that has already passed.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun HourEditor(
    plan: Plan,
    mine: String?,
    now: ZonedDateTime,
    busy: Boolean,
    onOfferHour: (String) -> Unit,
) {
    if (!canOfferHour(plan)) return
    val agreed = plan.startsAt

    var editing by remember { mutableStateOf(false) }
    var chosenDay by remember { mutableStateOf<LocalDate?>(null) }
    var chosenHour by remember { mutableStateOf<Int?>(null) }

    val days = remember(now) { meetingDays(now) }
    if (days.isEmpty()) return
    val day = chosenDay?.takeIf { it in days } ?: days.first()
    val hours = remember(day, now) { meetingHours(day, now) }
    val hour = chosenHour?.takeIf { it in hours } ?: hours.first()

    if (!editing) {
        AppButton(
            text = offerButtonLabel(mine, agreed, now),
            onClick = { editing = true },
            enabled = !busy,
            variant = AppButtonVariant.Ghost,
            modifier = Modifier.fillMaxWidth(),
        )
        return
    }
    Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
        Text(
            "КОГДА ВАМ УДОБНО",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            days.forEach { date ->
                InterestChip(label = meetingDayLabel(date, now), selected = date == day, onClick = { chosenDay = date })
            }
        }
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            hours.forEach { candidate ->
                InterestChip(label = meetingHourLabel(candidate), selected = candidate == hour, onClick = { chosenHour = candidate })
            }
        }
        AppButton(
            text = "Предложить: ${meetingDayLabel(day, now)}, ${meetingHourLabel(hour)}",
            onClick = {
                onOfferHour(meetingInstant(day, hour, ZoneId.systemDefault()))
                editing = false
            },
            enabled = !busy,
            variant = AppButtonVariant.Tonal,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

/**
 * The two words of the pair — its place and its note — opened on the card that holds them.
 *
 * The fields start from what the server already holds, so an emptied one is a decision to take the
 * word back rather than a blank nobody meant, and a field the person never touched sends nothing at
 * all: the write below reads both against the stored row. The editor closes when the words the
 * server holds catch up with what was typed — «сохранено» says the reloaded row, not a flag this
 * screen invented — and a refusal leaves the typed text where it was, because losing a note the
 * server would not take is the worse of the two endings.
 */
@Composable
private fun WordsEditor(
    plan: Plan,
    busy: Boolean,
    onSaveWords: (String, String) -> Unit,
) {
    var open by remember { mutableStateOf(false) }
    var placeText by remember { mutableStateOf(plan.place.orEmpty()) }
    var noteText by remember { mutableStateOf(plan.note.orEmpty()) }
    var sent by remember { mutableStateOf(false) }

    val storedPlace = plan.place.orEmpty().trim()
    val storedNote = plan.note.orEmpty().trim()
    val synced = placeText.trim() == storedPlace && noteText.trim() == storedNote

    if (!open) {
        if (storedPlace.isNotEmpty()) {
            Text(
                "Место: $storedPlace",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (storedNote.isNotEmpty()) {
            Text(
                "Заметка пары: $storedNote",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        AppButton(
            text = if (storedPlace.isEmpty() && storedNote.isEmpty()) "Где встречаемся?" else "Изменить место или заметку",
            onClick = {
                placeText = plan.place.orEmpty()
                noteText = plan.note.orEmpty()
                sent = false
                open = true
            },
            enabled = !busy,
            variant = AppButtonVariant.Ghost,
            modifier = Modifier.fillMaxWidth(),
        )
        return
    }

    LaunchedEffect(busy, synced, sent) {
        if (sent && !busy && synced) {
            sent = false
            open = false
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
        AppTextField(
            value = placeText,
            onValueChange = { placeText = it },
            label = "Место",
            placeholder = "Например, кофейня у парка",
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Next),
            modifier = Modifier.fillMaxWidth(),
        )
        AppTextField(
            value = noteText,
            onValueChange = { noteText = it },
            label = "Заметка пары",
            placeholder = "Что важно для этой встречи",
            singleLine = false,
            minLines = 2,
            maxLines = 4,
            modifier = Modifier.fillMaxWidth(),
        )
        Text(
            "Обе строки видны вам обоим. Пустое поле снимает то, что было написано.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        AppButton(
            text = "Сохранить",
            onClick = {
                sent = true
                onSaveWords(placeText, noteText)
            },
            enabled = !busy && !synced,
            variant = AppButtonVariant.Tonal,
            modifier = Modifier.fillMaxWidth(),
        )
        QuietAction("Отмена", busy = false) {
            sent = false
            open = false
        }
    }
}

/** A tap that ends or reverses something the pair holds, kept quiet and after the main one. */
@Composable
private fun ColumnScope.QuietAction(text: String, busy: Boolean, onClick: () -> Unit) {
    TextButton(onClick = onClick, enabled = !busy, modifier = Modifier.align(Alignment.End)) {
        Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** The state the card is in, read as a badge rather than as a sentence the title would have to share. */
@Composable
private fun StatusBadge(text: String, accent: Color) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(12.dp))
            .background(accent.copy(alpha = 0.12f))
            .border(Elev.hairlineWidth, accent.copy(alpha = 0.35f), RoundedCornerShape(12.dp))
            .padding(horizontal = Spacing.md, vertical = 4.dp),
    ) {
        Text(
            text,
            color = accent,
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Bold,
        )
    }
}
