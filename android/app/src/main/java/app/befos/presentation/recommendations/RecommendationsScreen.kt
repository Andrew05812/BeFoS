package app.befos.presentation.recommendations

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.EmberDeep
import app.befos.core.designsystem.EmberSoft
import app.befos.core.designsystem.Elev
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.ListSkeleton
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.cardPaintedSurface
import app.befos.core.designsystem.scoreColor
import app.befos.core.designsystem.scoreTextColorOnWash
import app.befos.core.designsystem.tabularDigits
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.Recommendation
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZonedDateTime

@Composable
fun RecommendationsScreen(matchId: String, onBack: () -> Unit) {
    val vm: RecommendationsViewModel =
        beFosViewModel { RecommendationsViewModel(it.matchRepository, it.chatRepository, matchId) }
    val state by vm.uiState.collectAsState()
    // Refused ideas stay on the page rather than vanishing from it: what is hidden is the card's
    // place in the list, not its record, so the same data carries both sections.
    val (refused, ideas) = remember(state.items, state.declined) {
        state.items.partition { state.declined.contains(it.activity.id) }
    }
    // Reasons carried by every idea in the list are facts about the pair, not about
    // the idea; they are shown once above the list instead of eight times inside it.
    val shared = remember(state.items) {
        state.items.map { it.reasons.toSet() }.reduceOrNull { a, b -> a intersect b }.orEmpty()
    }

    Scaffold(
        topBar = { AppTopBar(title = "Идеи для встречи", onBack = onBack) },
    ) { padding ->
        when {
            state.loading -> ListSkeleton(Modifier.padding(padding), rows = 4)
            state.error != null && state.items.isEmpty() -> ErrorState(
                message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
                title = "Не удалось загрузить идеи",
                onRetry = vm::load,
                modifier = Modifier.padding(padding),
            )
            state.items.isEmpty() -> EmptyState(
                title = "Идей пока нет",
                message = "Пока нет предложений для этой пары. Рекомендации обновляются вместе с анкетами — загляните позже.",
                overline = "Свидания",
                actionLabel = "Обновить",
                onAction = vm::load,
                modifier = Modifier.padding(padding),
            )
            else -> LazyColumn(
                modifier = Modifier.padding(padding).fillMaxSize().padding(horizontal = Spacing.gutter),
                verticalArrangement = Arrangement.spacedBy(Spacing.lg),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = Spacing.lg),
            ) {
                if (state.selectError != null) {
                    item {
                        // The card stays marked while the notice is about its record: the idea is
                        // readable in chat either way, and only the mark is missing.
                        val canRetry = state.unsavedChoices.isNotEmpty()
                        InlineNotice(
                            text = state.selectError.orEmpty(),
                            actionLabel = "Повторить".takeIf { canRetry },
                            onAction = if (canRetry) vm::retryRecords else null,
                        )
                    }
                }
                if (state.declineError != null) {
                    // No «Повторить» beside this one: the card came back to the list, so the tap
                    // that failed is its own retry, and a second button would offer one decision
                    // under two names.
                    item { InlineNotice(text = state.declineError.orEmpty()) }
                }
                item {
                    Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                        Text(
                            "ПОДОБРАНО ДЛЯ ВАС ДВОИХ",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        // «под каждой указано, почему она подходит» was a promise the engine could not
                        // always keep: a bullet is printed only where the pair's own answers support
                        // one, so an idea can honestly arrive without a note. This wording says what
                        // the list holds instead of counting the lines on each card.
                        Text(
                            "Идеи выросли из ваших анкет и ответов в тесте. Под карточкой — только то, что правда для вас двоих.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        // A reason printed under every single idea describes the pair, not
                        // the idea, and eight copies of it read as boilerplate. It gets one
                        // home here so what is left on the card is what actually differs.
                        if (shared.isNotEmpty()) {
                            Spacer(Modifier.height(Spacing.sm))
                            Text(
                                "ЧТО У ВАС ОБЩЕГО",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                                // Same bullet language as the cards, in a neutral tint: the
                                // accent belongs to the idea's own score, not to a fact
                                // printed above the whole list.
                                shared.forEach { reason ->
                                    Row(
                                        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                                        verticalAlignment = Alignment.Top,
                                    ) {
                                        Box(
                                            Modifier
                                                .padding(top = 7.dp)
                                                .size(6.dp)
                                                .clip(CircleShape)
                                                .background(MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.45f)),
                                        )
                                        Text(reason, style = MaterialTheme.typography.bodySmall)
                                    }
                                }
                            }
                        }
                    }
                }
                if (ideas.isEmpty()) {
                    item {
                        Text(
                            "Здесь не осталось идей — все с этой страницы вы отклонили.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                items(ideas, key = { it.activity.id }) { rec ->
                    RecommendationCard(
                        rec = rec,
                        hidden = shared,
                        selected = state.selected.contains(rec.activity.id),
                        declined = false,
                        time = cardTime(rec, state),
                        onSelect = { vm.select(rec.activity.id, rec.activity.title) },
                        onDecline = { vm.decline(rec.activity.id) },
                        onRestore = null,
                        onProposeTime = { whenIso -> vm.proposeTime(rec.activity.id, whenIso) },
                        onAcceptTime = { whenIso -> vm.acceptTime(rec.activity.id, whenIso) },
                    )
                }
                if (refused.isNotEmpty()) {
                    item {
                        Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                            Text(
                                "ВЫ ОТКЛОНИЛИ (${refused.size})",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            // Says whose list this is, because it is the whole point of the section:
                            // the partner keeps seeing the idea, and nothing about the refusal
                            // reaches them.
                            Text(
                                "Эти идеи скрыты только у вас: партнёр видит их в своей подборке и не узнаёт об отказе. Любую можно вернуть.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    items(refused, key = { it.activity.id }) { rec ->
                        RecommendationCard(
                            rec = rec,
                            hidden = shared,
                            selected = state.selected.contains(rec.activity.id),
                            declined = true,
                            time = cardTime(rec, state),
                            onSelect = { vm.select(rec.activity.id, rec.activity.title) },
                            onDecline = null,
                            onRestore = { vm.restore(rec.activity.id) },
                            onProposeTime = { whenIso -> vm.proposeTime(rec.activity.id, whenIso) },
                            onAcceptTime = { whenIso -> vm.acceptTime(rec.activity.id, whenIso) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun RecommendationCard(
    rec: Recommendation,
    hidden: Set<String>,
    selected: Boolean,
    declined: Boolean,
    time: CardTime,
    onSelect: () -> Unit,
    onDecline: (() -> Unit)?,
    onRestore: (() -> Unit)?,
    onProposeTime: (String) -> Unit,
    onAcceptTime: (String) -> Unit,
) {
    val accent = scoreColor(rec.score)
    // Never empty a card of its explanation: when the pair-level fact above is the only
    // thing this idea has going for it, it stays here instead of moving to the header.
    val reasons = if (rec.reasons.size > 1) rec.reasons.filterNot { it in hidden } else rec.reasons
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
                    rec.activity.title,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f, fill = false),
                )
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(12.dp))
                        .background(accent.copy(alpha = 0.12f))
                        .border(Elev.hairlineWidth, accent.copy(alpha = 0.35f), RoundedCornerShape(12.dp))
                        .padding(horizontal = Spacing.md, vertical = 4.dp),
                ) {
                    Text(
                        "${rec.score}%",
                        color = scoreTextColorOnWash(rec.score, cardPaintedSurface()),
                        style = MaterialTheme.typography.labelLarge.tabularDigits(),
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
            if (!rec.activity.description.isNullOrBlank()) {
                Text(
                    rec.activity.description,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (reasons.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
                    Text(
                        "ПОЧЕМУ ПОДХОДИТ",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    reasons.forEach { reason ->
                        Row(
                            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                            verticalAlignment = Alignment.Top,
                        ) {
                            Box(
                                Modifier
                                    .padding(top = 7.dp)
                                    .size(6.dp)
                                    .clip(CircleShape)
                                    .background(accent),
                            )
                            Text(reason, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
            when {
                declined -> {
                    // Kept readable instead of deleted: the reason this idea was chosen for the
                    // pair is the text that explains what «Вернуть» would put back.
                    ChoiceChip(
                        "Идея осталась в чате, но вы её отклонили".takeIf { selected }
                            ?: "Вы отклонили эту идею",
                        Icons.Filled.Close,
                        MaterialTheme.colorScheme.surfaceVariant,
                        MaterialTheme.colorScheme.onSurfaceVariant,
                        MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    onRestore?.let { action ->
                        AppButton(
                            text = "Вернуть в подборку",
                            onClick = action,
                            variant = AppButtonVariant.Ghost,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                }
                selected -> ChoiceChip(
                    "Эту идею выбрали вы оба".takeIf { rec.partnerSelected } ?: "Отправлено в чат",
                    Icons.Filled.CheckCircle,
                    EmberSoft,
                    EmberDeep,
                    MaterialTheme.colorScheme.primary,
                )
                else -> {
                    if (rec.partnerSelected) {
                        // Named before the button rather than instead of it: the idea is in the chat
                        // already, and this tap is the pair's answer to it, not a second proposal.
                        ChoiceChip(
                            "Её уже предложил партнёр",
                            Icons.AutoMirrored.Filled.Send,
                            MaterialTheme.colorScheme.surfaceVariant,
                            MaterialTheme.colorScheme.onSurfaceVariant,
                            MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    AppButton(
                        text = "Поддержать в чате".takeIf { rec.partnerSelected } ?: "Предложить в чате",
                        onClick = onSelect,
                        variant = AppButtonVariant.Tonal,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
            onDecline?.let { action ->
                // Quiet and beside the CTA rather than instead of it: an idea can go into the chat
                // and still be pushed away later, and the two taps mean different things to the
                // pair — one writes into the conversation, the other edits only this list.
                TextButton(onClick = action, modifier = Modifier.align(Alignment.End)) {
                    Text(
                        "Не подходит",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            MeetingTimeSection(
                time = time,
                // The hour belongs to an idea the pair is already talking about, so the editor opens
                // only for a card this person sent into the chat. Agreeing is not gated the same way:
                // the other half's hour is on the card either way, and a yes to it is an answer the
                // pair has not asked anyone to write first.
                canOffer = selected && !declined,
                canAgree = !declined,
                onProposeTime = onProposeTime,
                onAcceptTime = onAcceptTime,
            )
        }
    }
}

/**
 * What one card holds about the pair's plan: the hours the page reported, the hour this visit's tap
 * wrote, and the reason the last time tap did not land.
 */
private data class CardTime(
    val mine: String?,
    val partner: String?,
    val agreed: String?,
    val iAccepted: String?,
    val failure: String?,
)

private fun cardTime(rec: Recommendation, state: RecommendationsUiState): CardTime = CardTime(
    // The tap of this visit answers before the page does: an hour this person named stays on the
    // card even while a read that started earlier reports the row without one.
    mine = state.myOffers[rec.activity.id] ?: rec.myMeetingTime,
    partner = rec.partnerMeetingTime,
    agreed = state.agreedMoments[rec.activity.id] ?: rec.agreedTime,
    iAccepted = rec.iAcceptedTime,
    failure = state.timeErrors[rec.activity.id],
)

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun MeetingTimeSection(
    time: CardTime,
    canOffer: Boolean,
    canAgree: Boolean,
    onProposeTime: (String) -> Unit,
    onAcceptTime: (String) -> Unit,
) {
    // The clock is read once for this card, not once per recomposition: an hour row that recomputed
    // itself mid-glance could drop a chip under the finger already aiming at it.
    val now = remember { ZonedDateTime.now() }
    val plan = time.agreed
    val partnerOffer = time.partner
    val mine = time.mine
    // Which hour to offer is a decision being made, not a fact about the pair, so it never enters
    // the view state: the screen holds it until the tap that sends it.
    var editing by remember { mutableStateOf(false) }
    var chosenDay by remember { mutableStateOf<LocalDate?>(null) }
    var chosenHour by remember { mutableStateOf<Int?>(null) }

    val days = remember(now) { meetingDays(now) }
    val day = chosenDay?.takeIf { it in days } ?: days.first()
    val hours = remember(day, now) { meetingHours(day, now) }
    val hour = chosenHour?.takeIf { it in hours } ?: hours.first()

    Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        if (plan != null) {
            ChoiceChip(
                "Договорились: ${formatMeetingInstant(plan, now)}",
                Icons.Filled.CheckCircle,
                EmberSoft,
                EmberDeep,
                MaterialTheme.colorScheme.primary,
            )
        } else {
            if (partnerOffer != null) {
                ChoiceChip(
                    "Партнёр предлагает: ${formatMeetingInstant(partnerOffer, now)}",
                    Icons.AutoMirrored.Filled.Send,
                    MaterialTheme.colorScheme.surfaceVariant,
                    MaterialTheme.colorScheme.onSurfaceVariant,
                    MaterialTheme.colorScheme.onSurfaceVariant,
                )
                if (canAgree) {
                    // The instant goes back exactly as this card read it, so an offer the partner has
                    // moved in the meantime is refused rather than agreed to silently.
                    AppButton(
                        text = "Подходит",
                        onClick = { onAcceptTime(partnerOffer) },
                        variant = AppButtonVariant.Tonal,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
            if (time.iAccepted != null && partnerOffer != null && time.iAccepted != partnerOffer) {
                // Not a plan and not nothing: the yes was real, and the hour it answered is gone. The
                // card says both, because either sentence alone leaves the person guessing.
                Text(
                    "Вы соглашались на ${formatMeetingInstant(time.iAccepted, now)}, но партнёр назвал другой час.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (mine != null) {
                ChoiceChip(
                    "Вы предложили: ${formatMeetingInstant(mine, now)}",
                    Icons.Filled.Schedule,
                    MaterialTheme.colorScheme.surfaceVariant,
                    MaterialTheme.colorScheme.onSurfaceVariant,
                    MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (canOffer) {
                if (editing) {
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
                                InterestChip(
                                    label = meetingDayLabel(date, now),
                                    selected = date == day,
                                    onClick = { chosenDay = date },
                                )
                            }
                        }
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                        ) {
                            hours.forEach { candidate ->
                                InterestChip(
                                    label = meetingHourLabel(candidate),
                                    selected = candidate == hour,
                                    onClick = { chosenHour = candidate },
                                )
                            }
                        }
                        AppButton(
                            text = "Предложить: ${meetingDayLabel(day, now)}, ${meetingHourLabel(hour)}",
                            onClick = {
                                onProposeTime(meetingInstant(day, hour, ZoneId.systemDefault()))
                                editing = false
                            },
                            variant = AppButtonVariant.Tonal,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                } else {
                    AppButton(
                        text = if (mine == null) "Договориться о времени" else "Изменить время",
                        onClick = { editing = true },
                        variant = AppButtonVariant.Ghost,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
        time.failure?.let { failure ->
            // Named on the card it belongs to: an hour the server refused for one idea is not a
            // reason to doubt another one's plan.
            InlineNotice(text = failure)
        }
    }
}

@Composable
private fun ChoiceChip(
    text: String,
    icon: ImageVector,
    surface: Color,
    content: Color,
    tint: Color,
) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
        modifier = Modifier
            .clip(RoundedCornerShape(12.dp))
            .background(surface)
            .padding(horizontal = Spacing.md, vertical = Spacing.sm),
    ) {
        Icon(icon, contentDescription = null, tint = tint)
        Text(
            text,
            color = content,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}
