package app.befos.presentation.plans

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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Schedule
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
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
import app.befos.domain.model.Plan
import app.befos.domain.model.PlanDecisions
import app.befos.domain.model.PlanStatuses
import app.befos.presentation.common.planMomentPassed
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
) {
    val vm: PlansViewModel =
        beFosViewModel { PlansViewModel(it.planRepository, it.chatRepository, matchId) }
    val state by vm.uiState.collectAsState()
    val sections = remember(state.plans) { planSections(state.plans) }
    val listState = rememberLazyListState()
    // A refused refresh that leaves the cards standing costs its own row over the list, so the row a
    // tap from the chat leads to is counted from the same flags the list reads.
    val headerRows = 1 + (if (state.error != null) 1 else 0) + (if (state.outdated != null) 1 else 0)
    val focusRow = focusPlanId?.let { planFocusRow(it, sections, headerRows) }
    LaunchedEffect(focusRow, state.loading) {
        if (!state.loading && focusRow != null) listState.scrollToItem(focusRow)
    }
    // The clock is read once for the visit, not once per recomposition: a card whose hour row
    // recomputed itself mid-glance could drop a chip under the finger already aiming at it.
    val now = remember { ZonedDateTime.now() }

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
                val superseded = plan.status == PlanStatuses.RESCHEDULED
                val passed = planMomentPassed(plan.startsAt, now)
                ChoiceChip(
                    hour,
                    if (passed || superseded) Icons.Filled.Schedule else Icons.Filled.CheckCircle,
                    selected = !passed && !superseded,
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
            when {
                // A refusal is this person's own edit of their answer, so the way back is offered to
                // the one who refused — and only while the plan is still an idea rather than a
                // договорённость the other half has already stood on.
                plan.myDecision == PlanDecisions.DECLINED &&
                    (plan.status == PlanStatuses.PROPOSED || plan.status == PlanStatuses.DECLINED) ->
                    QuietAction("Вернуть идею", busy, onRestoreDecline)
                plan.status == PlanStatuses.PROPOSED -> {
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
            if (plan.canCancel) QuietAction("Отменить план", busy, onCancel)
            if (plan.status == PlanStatuses.CANCELLED) {
                AppButton(
                    text = "Вернуть план",
                    onClick = onRestore,
                    enabled = !busy,
                    variant = AppButtonVariant.Ghost,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
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
            error?.let { InlineNotice(text = it) }
        }
    }
}

/**
 * The hour row, opened only for a plan this person may still move.
 *
 * Which evening to offer is a decision being made, not a fact about the pair, so it never enters the
 * view state — the card holds it until the tap that sends it. The offers close over a plan the pair
 * still stands on and come back once that hour is behind them, because then the only thing left to
 * arrange is the next evening, and the server refuses a moment that has already passed.
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
    if (agreed != null && !planMomentPassed(agreed, now)) return

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
