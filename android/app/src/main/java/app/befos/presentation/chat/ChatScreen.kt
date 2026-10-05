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
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
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
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppTopBar
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
import kotlinx.coroutines.delay
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

@Composable
fun ChatScreen(
    matchId: String,
    onBack: () -> Unit,
    onOpenCompatibility: () -> Unit,
    onOpenRecommendations: () -> Unit,
) {
    val vm: ChatViewModel = beFosViewModel { ChatViewModel(it.chatRepository, it.matchRepository, matchId) }
    val state by vm.uiState.collectAsState()
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
                title = state.partnerName ?: "Чат",
                onBack = onBack,
                actions = {
                    IconButton(onClick = onOpenCompatibility) {
                        Icon(Icons.Filled.Insights, contentDescription = "Совместимость")
                    }
                    IconButton(onClick = onOpenRecommendations) {
                        Icon(Icons.Filled.AutoAwesome, contentDescription = "Идеи для встречи")
                    }
                },
            )
        },
        bottomBar = {
            ChatInputBar(
                draft = state.draft,
                onDraftChange = vm::onDraftChange,
                onSend = vm::send,
                enabled = !state.sending,
                sending = state.sending,
                sendError = state.sendError,
                onDismissError = vm::dismissSendError,
            )
        },
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            // Tidy status pill — no raw technical wording for the user.
            // It takes its own row: floated over the list it covered the first bubble.
            if (!state.loading && !state.connected) {
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

            Box(Modifier.weight(1f).fillMaxWidth()) {
                when {
                    state.loading -> ListSkeleton(rows = 6)
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
                            // tight inside, clear air when the speaker changes.
                            val continues = previous != null && previous.isOwn == message.isOwn
                            Column(modifier = Modifier.padding(top = if (continues) Spacing.xs else Spacing.lg)) {
                                MessageBubble(
                                    body = message.body,
                                    isOwn = message.isOwn,
                                    footer = if (message.isOwn && message.isRead) {
                                        "прочитано"
                                    } else {
                                        formatTime(message.createdAt)
                                    },
                                )
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
