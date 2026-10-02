package app.befos.presentation.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
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
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.LoadingState
import app.befos.core.designsystem.MessageBubble
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
                    title = "Сообщений пока нет",
                    message = "Напишите первым — сообщение доставится мгновенно.",
                )
                else -> LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 12.dp),
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
                Text(
                    "печатает…",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.align(Alignment.BottomStart).padding(start = 20.dp, bottom = 8.dp),
                )
            }
            if (!state.loading && !state.connected) {
                Row(
                    modifier = Modifier
                        .align(Alignment.TopCenter)
                        .fillMaxWidth()
                        .background(MaterialTheme.colorScheme.surfaceVariant)
                        .padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        "Подключение… переподключаемся",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
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
    Row(
        modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)
            .navigationBarsPadding().imePadding().padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        AppTextField(
            value = draft,
            onValueChange = onDraftChange,
            label = "",
            placeholder = "Сообщение…",
            singleLine = false,
            maxLines = 4,
            modifier = Modifier.weight(1f),
        )
        IconButton(onClick = onSend, enabled = enabled && draft.isNotBlank()) {
            Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Отправить", tint = MaterialTheme.colorScheme.primary)
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
