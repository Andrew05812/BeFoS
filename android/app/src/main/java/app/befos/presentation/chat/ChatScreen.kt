package app.befos.presentation.chat

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Event
import androidx.compose.material.icons.filled.Flag
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.SupervisorAccount
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.Ember
import app.befos.core.designsystem.EmberGradient
import app.befos.core.designsystem.Elev
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.ListSkeleton
import app.befos.core.designsystem.MessageBubble
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.WarningAmber
import app.befos.core.designsystem.rememberHaptics
import app.befos.core.di.beFosViewModel
import app.befos.core.network.CHAT_CLOSED
import app.befos.core.network.CHAT_CLOSED_DETAIL
import app.befos.domain.model.Message
import app.befos.domain.model.MessageKinds
import app.befos.presentation.common.ReportDialog
import app.befos.presentation.common.PLAN_PAST_WORD
import app.befos.presentation.common.planMomentPassed
import kotlinx.coroutines.delay
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun ChatScreen(
    matchId: String,
    initialDraft: String?,
    onBack: () -> Unit,
    onOpenCompatibility: () -> Unit,
    onOpenRecommendations: () -> Unit,
    onOpenPlans: () -> Unit,
    // The pair's own reading of itself — who they are, what the engine compared, the hour they stand on.
    // The thread is where a pair lives, so it is where the door to that page belongs; the page adds no
    // editor, so opening it from here cannot put the pair anywhere they did not ask to be.
    onOpenPairProfile: () -> Unit,
    // Where a plan line leads: the plan id the line names, and the idea it was about as the way out
    // for a line written before the id existed.
    onOpenPlan: (String?, Int?) -> Unit,
    onOpenPartnerCard: () -> Unit,
) {
    val vm: ChatViewModel = beFosViewModel {
        ChatViewModel(it.chatRepository, it.matchRepository, it.safetyRepository, matchId, initialDraft)
    }
    val state by vm.uiState.collectAsState()
    val reportState by vm.report.state.collectAsState()
    val haptics = rememberHaptics()

    // A line that was meant to leave the thread and stayed says nothing the reader can act on
    // twice: the notice names the failed tap, and the thread itself is unchanged by it.
    LaunchedEffect(state.recallError) {
        if (state.recallError != null) {
            delay(Motion.Notice.toLong())
            vm.dismissRecallError()
        }
    }

    state.recallConfirmation?.let { line ->
        AlertDialog(
            onDismissRequest = vm::cancelRecall,
            title = { Text("Забрать сообщение?") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                    Text(
                        // The words go with the question, because they are the last place they can
                        // still be read: the answer erases them from the server and from both
                        // screens, and a confirmation that named only the moment of the line would
                        // ask about something the person cannot check.
                        text = "«${line.body}»",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 4,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Text(
                        "Сообщение исчезнет из переписки у вас и у собеседника и не вернётся. " +
                            "Если собеседник уже успел его прочесть, этого не отменить — у него останется то, что он прочитал.",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = vm::confirmRecall) {
                    Text("Забрать сообщение", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = { TextButton(onClick = vm::cancelRecall) { Text("Отмена") } },
        )
    }

    if (reportState.open) {
        ReportDialog(
            state = reportState,
            onReason = vm.report::setReason,
            onDetails = vm.report::setDetails,
            onSubmit = vm.report::submit,
            onDismiss = vm::closeReport,
        )
    }
    val listState = rememberLazyListState()
    // Following every incoming message would yank the reader back down while they are
    // still looking at older parts of the conversation.
    val atBottom by remember {
        derivedStateOf {
            val info = listState.layoutInfo
            val lastVisible = info.visibleItemsInfo.lastOrNull()
            lastVisible == null || lastVisible.index >= info.totalItemsCount - 1
        }
    }

    LaunchedEffect(state.messages.size) {
        if (state.messages.isNotEmpty() && atBottom) {
            listState.animateScrollToItem(state.messages.lastIndex)
        }
    }

    Scaffold(
        topBar = {
            AppTopBar(
                // The same word the empty state uses for a partner whose name has not arrived:
                // «Чат» is the name of the screen, not of the person the thread is with.
                title = state.partnerName ?: "Собеседник",
                onBack = onBack,
                actions = {
                    // The card the deck no longer serves: a mutual match takes the person out of
                    // the queue, so without this action the closest person in the product is the
                    // one whose «о себе», interests and age cannot be read a second time.
                    IconButton(onClick = onOpenPartnerCard) {
                        Icon(Icons.Filled.Person, contentDescription = "Анкета собеседника")
                    }
                    // The complaint belongs to the conversation, not to the composer: a thread the
                    // server has closed for messages is exactly where the reason to report someone
                    // was written down. What it does need is the id naming the person, and that only
                    // arrives with the partner's card.
                    IconButton(onClick = vm::askReport, enabled = state.partnerUserId != null) {
                        Icon(Icons.Filled.Flag, contentDescription = "Пожаловаться")
                    }
                    IconButton(onClick = onOpenCompatibility) {
                        Icon(Icons.Filled.Insights, contentDescription = "Совместимость")
                    }
                    // The two of them as one reading, next to the two readings of each of them: the person
                    // card above answers one half, this answers the pair.
                    IconButton(onClick = onOpenPairProfile) {
                        Icon(Icons.Filled.SupervisorAccount, contentDescription = "Профиль пары")
                    }
                    IconButton(onClick = onOpenRecommendations) {
                        Icon(Icons.Filled.AutoAwesome, contentDescription = "Идеи для встречи")
                    }
                    // The arrangement the pair has already landed on is not an idea still being
                    // looked for: the thread writes a line per move, and this is the page that holds
                    // the plan those lines are about.
                    IconButton(onClick = onOpenPlans) {
                        Icon(Icons.Filled.Event, contentDescription = "Наши планы")
                    }
                },
            )
        },
        bottomBar = {
            // A thread the server refuses as gone cannot receive a message, so the field that
            // would send one is held back rather than left to fail on every tap — the same call
            // the card of a formed pair makes about «Нравится» and «Пропустить».
            if (!state.gone) {
                ChatInputBar(
                    draft = state.draft,
                    onDraftChange = vm::onDraftChange,
                    onSend = vm::send,
                    enabled = !state.sending,
                    sending = state.sending,
                    sendError = state.sendError,
                    onDismissError = vm::dismissSendError,
                )
            }
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            // Tidy status pill — no raw technical wording for the user.
            // It takes its own row: floated over the list it covered the first bubble.
            // A gone thread is named below, and the pill's fallback line would promise a
            // recovery the dial has already stopped attempting.
            if (!state.loading && !state.connected && !state.gone) {
                Row(
                    modifier = Modifier
                        .align(Alignment.CenterHorizontally)
                        .padding(bottom = Spacing.xs)
                        .clip(RoundedCornerShape(18.dp))
                        .background(WarningAmber.copy(alpha = 0.12f))
                        .border(Elev.hairlineWidth, WarningAmber.copy(alpha = 0.38f), RoundedCornerShape(18.dp))
                        .padding(horizontal = Spacing.lg, vertical = Spacing.sm),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    Box(Modifier.size(7.dp).clip(CircleShape).background(WarningAmber))
                    Text(
                        // The dot already says the socket is down; the words say why, so the
                        // user learns it is the network, the server or a pair that is gone.
                        state.socketReason ?: "Соединение восстанавливается",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            // A gap the reconnect could not read is named over the thread instead of left
            // invisible behind a pill that says the link is back. It stays until the read
            // itself answers: a bubble arriving live does not close the page still missing.
            if (state.messages.isNotEmpty() && state.historyError != null) {
                InlineNotice(
                    text = state.historyError!! + " Часть сообщений за паузу могла не показаться.",
                    modifier = Modifier
                        .padding(horizontal = Spacing.gutter)
                        .padding(bottom = Spacing.xs),
                    actionLabel = if (state.gone) null else "Повторить",
                    onAction = if (state.gone) null else vm::retryHistory,
                )
            }

            // A tap that did not erase anything leaves the line exactly where it was, so the thread
            // cannot report it: the words stay, the bubble stays, and only this notice says that the
            // answer came back refusing. It is placed over the thread rather than in the composer
            // because the composer belongs to a send, and nothing about this tap touched the draft.
            if (state.recallError != null) {
                InlineNotice(
                    text = state.recallError!!,
                    modifier = Modifier
                        .padding(horizontal = Spacing.gutter)
                        .padding(bottom = Spacing.xs),
                )
            }

            Box(Modifier.weight(1f).fillMaxWidth()) {
                when {
                    state.loading -> ListSkeleton(rows = 6)
                    state.messages.isEmpty() && state.gone -> EmptyState(
                        // The pair is gone, not unread: this is the screen's own terminal state,
                        // so it takes the wording the product already uses for a chat that closed
                        // and says what is still true of it, instead of repeating the advice the
                        // refused read carried — that advice was written for a list that reloads.
                        title = CHAT_CLOSED,
                        message = CHAT_CLOSED_DETAIL,
                        overline = "Переписка",
                    )
                    state.messages.isEmpty() && state.historyError != null -> ErrorState(
                        message = state.historyError!!,
                        title = "Не удалось загрузить переписку",
                        onRetry = vm::retryHistory,
                    )
                    state.messages.isEmpty() -> EmptyState(
                        title = "Начните разговор",
                        // "Пара увидит" is vague and slightly clinical; naming the person
                        // is warmer, and the promise is honest — there is no push, so the
                        // message really does wait for them to open the app.
                        message = if (state.partnerName != null) {
                            "Напишите первым — ${state.partnerName} увидит сообщение, когда откроет приложение."
                        } else {
                            "Напишите первым — собеседник увидит сообщение, когда откроет приложение."
                        },
                        overline = "Переписка",
                    )
                    else -> LazyColumn(
                        state = listState,
                        modifier = Modifier.fillMaxSize().padding(horizontal = Spacing.gutter),
                        contentPadding = androidx.compose.foundation.layout.PaddingValues(
                            top = Spacing.lg,
                            bottom = Spacing.xl,
                        ),
                    ) {
                        itemsIndexed(state.messages, key = { _, message -> message.id }) { index, message ->
                            val previous = state.messages.getOrNull(index - 1)
                            // Consecutive messages from one person read as one block:
                            // tight inside, clear air when the speaker changes. A line the pair's
                            // agreement wrote is not a person speaking, so it breaks the block on
                            // both sides instead of taking its neighbour's spacing.
                            val continues = previous != null && previous.isOwn == message.isOwn &&
                                previous.isPlanEvent == message.isPlanEvent
                            Column(modifier = Modifier.padding(top = if (continues) Spacing.xs else Spacing.lg)) {
                                if (message.isPlanEvent) {
                                    val ui = planCardUi(message, state.partnerName)
                                    PlanEventCard(ui = ui, onClick = { onOpenPlan(ui.planId, ui.activityId) })
                                } else {
                                    // Only a sentence somebody typed can be held: the lines the
                                    // pair's agreement writes record a plan that has its own
                                    // lifecycle, and a gesture that leads to a refusal the server
                                    // will answer on every kind but one is not offered for them.
                                    val hold: (() -> Unit)? = if (message.isOwn) {
                                        {
                                            haptics.light()
                                            vm.askRecall(message)
                                        }
                                    } else {
                                        null
                                    }
                                    MessageBubble(
                                        body = message.body,
                                        isOwn = message.isOwn,
                                        footer = if (message.isOwn && message.isRead) {
                                            "прочитано"
                                        } else {
                                            formatTime(message.createdAt)
                                        },
                                        onLongClick = hold,
                                        onLongClickLabel = if (message.isOwn) "Забрать сообщение" else null,
                                    )
                                }
                            }
                        }
                    }
                }

                if (state.otherTyping) {
                    TypingIndicator(Modifier.align(Alignment.BottomStart).padding(start = Spacing.gutter, bottom = Spacing.sm))
                }
            }
        }
    }
}

/** Three soft pulsing dots in an incoming-shaped bubble. */
@Composable
private fun TypingIndicator(modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "typing")
    val wave by transition.animateFloat(
        initialValue = 0f,
        targetValue = 3f,
        animationSpec = infiniteRepeatable(tween(1100, easing = LinearEasing), RepeatMode.Restart),
        label = "typingWave",
    )
    Row(
        modifier = modifier
            .clip(RoundedCornerShape(20.dp, 20.dp, 20.dp, 6.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant)
            .padding(horizontal = Spacing.lg, vertical = Spacing.md),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        repeat(3) { i ->
            val level = when {
                wave >= i + 1f -> 1f
                wave > i.toFloat() -> wave - i
                else -> 0.25f
            }
            Box(
                Modifier
                    .size(7.dp)
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.35f + 0.55f * level)),
            )
        }
    }
}

/**
 * What the plan card says, worked out away from Compose so the words can be read the way the
 * thread serves them: a promise a later tap took back, a moment that never arrived, an idea the
 * catalogue has dropped. Each of those has to be named on the card rather than painted over.
 */
internal data class PlanCardUi(
    val overline: String,
    val idea: String,
    val moment: String?,
    val status: String,
    val who: String,
    // The plan this line was written about, or null for a line the server wrote before plans had
    // their own rows. A pair can talk the same idea over more than once, so the idea alone does not
    // answer which plan the tap asked about — and a line without an id still leads somewhere.
    val planId: String?,
    // The idea the card leads to, or null when the line lost it: the tap still opens the pair's
    // ideas, just without a card to bring into view.
    val activityId: Int?,
    // Whether the line holds an agreement the pair is still keeping: the card takes its accent from
    // this rather than from a word, so a header rewrite cannot quietly restyle every card.
    val standing: Boolean,
)

/**
 * The header and the chip each kind of plan line is allowed to claim.
 *
 * The pair's plan writes a line per move, and the moves are not the same act: an idea put to the
 * pair has no hour yet, a rescheduled line names an hour the other half has not answered, a
 * completed one says the meeting happened. Only the two kinds that carry the hour the pair landed
 * on can be called standing, and only they can be walked past by the clock — so the words belong to
 * the kind, and a kind this build does not know says that on its face instead of falling through to
 * a promise nobody made.
 *
 * The plan's history page reads this same map: its rows are built from the very lines the chat draws,
 * and a second copy of the vocabulary would let the two screens start calling one move two different
 * things.
 */
internal data class PlanKindWords(
    val overline: String,
    val current: String,
    val superseded: String,
    val holdsAgreedHour: Boolean,
)

/** The word a live agreement is called on screen, and on the pair's own idea card. */
internal const val PLAN_STANDING_WORD = "действует"

private const val PLAN_SUPERSEDED_WORD = "позже пара сказала другое"

internal val PLAN_KIND_UNKNOWN = PlanKindWords(
    overline = "План пары",
    current = "эта версия приложения её не читает",
    superseded = PLAN_SUPERSEDED_WORD,
    holdsAgreedHour = false,
)

internal val PLAN_KIND_WORDS: Map<String, PlanKindWords> = mapOf(
    MessageKinds.PLAN_PROPOSED to PlanKindWords(
        overline = "Идея",
        current = "ждёт ответа",
        superseded = PLAN_SUPERSEDED_WORD,
        holdsAgreedHour = false,
    ),
    MessageKinds.PLAN_ACCEPTED to PlanKindWords(
        overline = "Идея",
        current = "подтверждена обоими, час не назван",
        superseded = PLAN_SUPERSEDED_WORD,
        holdsAgreedHour = false,
    ),
    MessageKinds.PLAN_DECLINED to PlanKindWords(
        overline = "Идея",
        current = "отклонена",
        superseded = PLAN_SUPERSEDED_WORD,
        holdsAgreedHour = false,
    ),
    MessageKinds.PLAN_AGREED to PlanKindWords(
        overline = "Договорённость",
        current = PLAN_STANDING_WORD,
        superseded = "отменена позже",
        holdsAgreedHour = true,
    ),
    MessageKinds.PLAN_RESCHEDULED to PlanKindWords(
        overline = "Договорённость",
        // The hour on this line is one half's offer, not the pair's agreement, so the card cannot
        // call it standing and cannot call it spent: the answer it waits for is the news.
        current = "новый час ждёт ответа",
        superseded = PLAN_SUPERSEDED_WORD,
        holdsAgreedHour = false,
    ),
    MessageKinds.PLAN_CHANGED to PlanKindWords(
        overline = "Договорённость",
        current = PLAN_STANDING_WORD,
        superseded = "отменена позже",
        holdsAgreedHour = true,
    ),
    MessageKinds.PLAN_CANCELLED to PlanKindWords(
        overline = "Договорённость",
        current = "отменена",
        superseded = PLAN_SUPERSEDED_WORD,
        holdsAgreedHour = false,
    ),
    MessageKinds.PLAN_COMPLETED to PlanKindWords(
        overline = "Договорённость",
        // Both halves said the meeting happened, so the clock has nothing left to report about it.
        current = "встреча состоялась",
        superseded = PLAN_SUPERSEDED_WORD,
        holdsAgreedHour = false,
    ),
    MessageKinds.PLAN_VOIDED to PlanKindWords(
        overline = "Договорённость",
        current = "отменена",
        superseded = PLAN_SUPERSEDED_WORD,
        holdsAgreedHour = false,
    ),
)

internal fun planCardUi(
    message: Message,
    partnerName: String?,
    zone: ZoneId = ZoneId.systemDefault(),
    now: ZonedDateTime = ZonedDateTime.now(zone),
): PlanCardUi {
    val plan = message.plan
    val words = PLAN_KIND_WORDS[message.kind] ?: PLAN_KIND_UNKNOWN
    val latest = plan?.isLatest == true
    // The hour the pair agreed on is behind them, and the row says nothing else: nobody retired it,
    // so the card cannot claim a promise that is still being kept.
    val passed = latest && words.holdsAgreedHour && planMomentPassed(plan?.whenIso, now)
    return PlanCardUi(
        overline = words.overline,
        // The name the server reads off the catalogue when the page is drawn, so a card that has
        // lost its idea says that instead of showing a blank where the meeting was about.
        idea = plan?.activityTitle ?: "Идея, о которой договаривались, больше недоступна",
        moment = formatPlanMoment(plan?.whenIso, zone),
        status = when {
            !latest -> words.superseded
            passed -> PLAN_PAST_WORD
            else -> words.current
        },
        who = "Вы и ${partnerName ?: "собеседник"}",
        planId = plan?.planId,
        activityId = plan?.activityId,
        standing = latest && !passed && words.holdsAgreedHour,
    )
}

/**
 * The agreed instant in the reader's own calendar, or null when the line carries none.
 *
 * A plan is always ahead of the tap that confirmed it, so the date goes with the hour: «19:00» on
 * its own would have the pair guess which day. A moment this build cannot parse is left out rather
 * than shown as the server's own text — an unreadable line already says too much about a plan.
 */
internal fun formatPlanMoment(iso: String?, zone: ZoneId): String? {
    if (iso.isNullOrBlank()) return null
    val when_ = runCatching { OffsetDateTime.parse(iso).atZoneSameInstant(zone) }.getOrNull() ?: return null
    return when_.format(DateTimeFormatter.ofPattern("d MMMM, HH:mm", Locale("ru")))
}

/**
 * The agreement as the thread shows it: a card, not a bubble.
 *
 * Nobody typed this line, so it takes neither the ember fill of a person's own message nor their
 * side of the thread — it stands across the column, and a pair that scrolls past it can tell an
 * agreement from a sentence at once. A cancelled promise keeps the same shape and loses the accent,
 * which is the honest reading of a row that records something the pair no longer holds.
 */
@Composable
private fun PlanEventCard(
    ui: PlanCardUi,
    onClick: () -> Unit,
) {
    val haptics = rememberHaptics()
    val active = ui.standing
    val shape = RoundedCornerShape(18.dp)
    val accent = if (active) Ember else MaterialTheme.colorScheme.onSurfaceVariant
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .widthIn(max = 380.dp)
            .clip(shape)
            .background(
                if (active) Ember.copy(alpha = 0.07f) else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.6f)
            )
            .border(
                width = Elev.hairlineWidth * 2f,
                color = if (active) Ember.copy(alpha = 0.42f) else MaterialTheme.colorScheme.outlineVariant,
                shape = shape,
            )
            .semantics { role = Role.Button }
            .clickable {
                haptics.light()
                onClick()
            }
            .padding(horizontal = Spacing.lg, vertical = Spacing.md),
        verticalArrangement = Arrangement.spacedBy(Spacing.xs),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            Box(
                Modifier
                    .size(8.dp)
                    .clip(CircleShape)
                    .background(if (active) Ember else MaterialTheme.colorScheme.outline)
            )
            Text(
                text = "${ui.overline} · ${ui.status}",
                style = MaterialTheme.typography.labelMedium,
                color = accent,
            )
        }
        Text(
            text = ui.idea,
            style = MaterialTheme.typography.titleSmall,
            color = MaterialTheme.colorScheme.onSurface,
            // An idea name the catalogue wrote in its own length must not push the moment and the
            // status off the screen; the tap leads to the card that holds the whole sentence.
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
        )
        if (ui.moment != null) {
            Text(
                text = ui.moment,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface,
            )
        }
        Text(
            text = ui.who,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            // The line's own plan when it names one, the pair's ideas when it does not: a card that
            // promised one destination and opened the other would leave the reader to find the plan
            // they tapped among a list of suggestions.
            text = if (ui.planId != null) "Открыть план пары" else "Открыть идеи пары",
            style = MaterialTheme.typography.labelMedium,
            color = accent,
        )
    }
}

@Composable
private fun ChatInputBar(
    draft: String,
    onDraftChange: (String) -> Unit,
    onSend: () -> Unit,
    enabled: Boolean,
    sending: Boolean,
    sendError: String?,
    onDismissError: () -> Unit,
) {
    val haptics = rememberHaptics()
    val canSend = enabled && draft.isNotBlank()
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.background.copy(alpha = 0.94f))
            .navigationBarsPadding()
            .imePadding(),
    ) {
        if (sendError != null) {
            LaunchedEffect(sendError) {
                delay(Motion.Notice.toLong())
                onDismissError()
            }
            InlineNotice(
                text = "$sendError Текст остался в поле — отправьте ещё раз.",
                modifier = Modifier.padding(horizontal = Spacing.gutter, vertical = Spacing.xs),
            )
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = Spacing.gutter, vertical = Spacing.md),
            verticalAlignment = Alignment.Bottom,
            horizontalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            Row(
                modifier = Modifier
                    .weight(1f)
                    .widthIn(min = 52.dp)
                    .clip(RoundedCornerShape(26.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant)
                    .border(
                        Elev.hairlineWidth,
                        MaterialTheme.colorScheme.outlineVariant,
                        RoundedCornerShape(26.dp),
                    )
                    .padding(start = Spacing.xl, end = Spacing.sm, top = Spacing.md, bottom = Spacing.md),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                BasicTextField(
                    value = draft,
                    onValueChange = onDraftChange,
                    maxLines = 4,
                    textStyle = MaterialTheme.typography.bodyLarge.copy(color = MaterialTheme.colorScheme.onSurface),
                    cursorBrush = SolidColor(MaterialTheme.colorScheme.primary),
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                    keyboardActions = KeyboardActions(
                        onSend = {
                            if (canSend) {
                                haptics.medium()
                                onSend()
                            }
                        },
                    ),
                    modifier = Modifier.weight(1f),
                    decorationBox = { inner ->
                        Box {
                            if (draft.isEmpty()) {
                                Text(
                                    "Сообщение…",
                                    style = MaterialTheme.typography.bodyLarge,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                            inner()
                        }
                    },
                )
            }
            Box(
                modifier = Modifier
                    .size(52.dp)
                    .clip(CircleShape)
                    .then(
                        if (canSend) {
                            Modifier.background(EmberGradient, CircleShape)
                        } else {
                            Modifier.background(MaterialTheme.colorScheme.surfaceVariant, CircleShape)
                        },
                    )
                    .semantics { role = Role.Button }
                    .then(
                        if (canSend) {
                            Modifier.clickable {
                                haptics.medium()
                                onSend()
                            }
                        } else {
                            Modifier
                        },
                    ),
                contentAlignment = Alignment.Center,
            ) {
                if (sending) {
                    // The draft is already cleared, so without this the tap looks lost.
                    CircularProgressIndicator(modifier = Modifier.size(22.dp), strokeWidth = 2.5.dp)
                } else {
                    Icon(
                        Icons.AutoMirrored.Filled.Send,
                        contentDescription = "Отправить",
                        tint = if (canSend) Color.White else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

private fun formatTime(iso: String): String {
    // The backend stamps UTC. Slicing the string showed server hours, not the
    // user's, so a message written at 10:48 read as 03:48.
    val sent = runCatching { OffsetDateTime.parse(iso).atZoneSameInstant(ZoneId.systemDefault()) }
        .getOrNull() ?: return ""
    val now = ZonedDateTime.now()
    return if (sent.toLocalDate() == now.toLocalDate()) {
        sent.format(DateTimeFormatter.ofPattern("HH:mm"))
    } else {
        sent.format(DateTimeFormatter.ofPattern("d MMM", Locale("ru")))
    }
}
