package app.befos.presentation.matches

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Badge
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AsyncAvatar
import app.befos.core.designsystem.LoadingBox
import app.befos.core.designsystem.MessagePane
import app.befos.core.designsystem.scoreColor
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.MatchSummary

@Composable
fun MatchListScreen(onOpenChat: (String) -> Unit) {
    val vm: MatchesViewModel = beFosViewModel { MatchesViewModel(it.matchRepository) }
    val state by vm.uiState.collectAsState()

    when {
        state.loading -> LoadingBox()
        state.error != null && state.matches.isEmpty() -> MessagePane(
            text = state.error ?: "Ошибка",
            title = "Не удалось загрузить пары",
            actionLabel = "Повторить",
            onAction = vm::load,
        )
        state.matches.isEmpty() -> MessagePane(
            text = "Когда вы и другой человек поставите друг другу «Нравится», здесь появится пара.",
            title = "Пар пока нет",
        )
        else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
            items(state.matches, key = { it.matchId }) { match ->
                MatchRow(match, onClick = { onOpenChat(match.matchId) })
                HorizontalDivider(color = MaterialTheme.colorScheme.surfaceVariant)
            }
        }
    }
}

@Composable
private fun MatchRow(match: MatchSummary, onClick: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick).padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box {
            AsyncAvatar(match.photoUrl, size = 56.dp)
            Box(
                modifier = Modifier.align(Alignment.BottomEnd).size(20.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    "${match.compatibility}",
                    color = scoreColor(match.compatibility),
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
        Column(modifier = Modifier.weight(1f)) {
            Text("${match.name}, ${match.age}", style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.SemiBold)
            Text(
                match.lastMessage ?: "Начните общение",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        if (match.unread > 0) {
            Badge(containerColor = MaterialTheme.colorScheme.primary) { Text("${match.unread}") }
        }
    }
}
