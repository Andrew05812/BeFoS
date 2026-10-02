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
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.EmberGradient
import app.befos.core.designsystem.Elev
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.LoadingState
import app.befos.core.designsystem.MessageBubble
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.WarningAmber
import app.befos.core.di.beFosViewModel

@Composable
fun ChatScreen(
    matchId: String,
    onBack: () -> Unit,
    onOpenCompatibility: () -> Unit,
    onOpenRecommendations: () -> Unit,
) {
    val vm: ChatViewModel = beFosViewModel { ChatViewModel(it.chatRepository, matchId) }
    val state by vm.uiState.collectAsState()
    val listState = rememberLazyListState()

    LaunchedEffect(state.messages.size) {
        if (state.messages.isNotEmpty()) listState.animateScrollToItem(state.messages.lastIndex)
    }

    Scaffold(
        topBar = {
            AppTopBar(
                title = "Чат",
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
            )
        },
    ) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) {
            when {
                state.loading -> LoadingState()
                state.messages.isEmpty() -> EmptyState(
                    title = "Начните разговор",
                    message = "Напишите первым — сообщение доставится мгновенно.",
                    overline = "Переписка",
                )
                else -> LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize().padding(horizontal = Spacing.gutter),
                    verticalArrangement = Arrangement.spacedBy(Spacing.xs),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(
                        top = Spacing.lg,
                        bottom = Spacing.xl,
                    ),
                ) {
                    items(state.messages, key = { it.id }) { message ->
                        MessageBubble(
                            body = message.body,
                            isOwn = message.isOwn,
                            footer = if (message.isOwn && message.isRead) "прочитано" else formatTime(message.createdAt),
                        )
                    }
                }
            }

            if (state.otherTyping) {
                TypingIndicator(Modifier.align(Alignment.BottomStart).padding(start = Spacing.gutter, bottom = Spacing.sm))
            }

            // Tidy status pill — no raw technical wording for the user.
            if (!state.loading && !state.connected) {
                Row(
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .padding(top = Spacing.md)
                        .clip(RoundedCornerShape(18.dp))
                        .background(WarningAmber.copy(alpha = 0.12f))
                        .border(Elev.hairlineWidth, WarningAmber.copy(alpha = 0.38f), RoundedCornerShape(18.dp))
                        .padding(horizontal = Spacing.lg, vertical = Spacing.sm),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                ) {
                    Box(Modifier.size(7.dp).clip(CircleShape).background(WarningAmber))
                    Text(
                        "Соединение восстанавливается",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
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
) {
    val canSend = enabled && draft.isNotBlank()
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(MaterialTheme.colorScheme.background.copy(alpha = 0.94f))
            .navigationBarsPadding()
            .imePadding()
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
                .then(
                    if (canSend) {
                        Modifier.clickable { onSend() }
                    } else {
                        Modifier
                    },
                ),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                Icons.AutoMirrored.Filled.Send,
                contentDescription = "Отправить",
                tint = if (canSend) Color.White else MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun formatTime(iso: String): String {
    // Backend sends ISO-8601; show the HH:MM portion when present.
    val t = iso.indexOf('T')
    if (t < 0) return iso
    val time = iso.substring(t + 1)
    return if (time.length >= 5) time.substring(0, 5) else time
}
