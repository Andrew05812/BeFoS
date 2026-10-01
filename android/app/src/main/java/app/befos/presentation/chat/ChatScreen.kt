package app.befos.presentation.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Insights
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.LoadingBox
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.Message

@OptIn(ExperimentalMaterial3Api::class)
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
            TopAppBar(
                title = { Text("Чат", fontWeight = FontWeight.SemiBold) },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад") }
                },
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
                state.loading -> LoadingBox()
                state.messages.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(
                        "Сообщений пока нет. Напишите первым!",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(24.dp),
                    )
                }
                else -> LazyColumn(
                    state = listState,
                    modifier = Modifier.fillMaxSize().padding(horizontal = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(vertical = 12.dp),
                ) {
                    items(state.messages, key = { it.id }) { message ->
                        MessageBubble(message)
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
        }
    }
}

@Composable
private fun MessageBubble(message: Message) {
    val own = message.isOwn
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (own) Arrangement.End else Arrangement.Start,
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 300.dp)
                .background(
                    color = if (own) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(
                        topStart = 18.dp,
                        topEnd = 18.dp,
                        bottomStart = if (own) 18.dp else 4.dp,
                        bottomEnd = if (own) 4.dp else 18.dp,
                    ),
                )
                .padding(horizontal = 14.dp, vertical = 8.dp),
        ) {
            Text(
                message.body,
                color = if (own) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(
                if (own && message.isRead) "прочитано" else formatTime(message.createdAt),
                style = MaterialTheme.typography.labelSmall,
                color = if (own) MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.7f) else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.align(Alignment.End),
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
    Row(
        modifier = Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface)
            .navigationBarsPadding().imePadding().padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        OutlinedTextField(
            value = draft,
            onValueChange = onDraftChange,
            placeholder = { Text("Сообщение…") },
            modifier = Modifier.weight(1f),
            maxLines = 4,
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
