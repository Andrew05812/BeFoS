package app.befos.presentation.matches

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.LoadingState
import app.befos.core.designsystem.MatchCard
import app.befos.core.designsystem.Spacing
import app.befos.core.di.beFosViewModel

@Composable
fun MatchListScreen(onOpenChat: (String) -> Unit) {
    val vm: MatchesViewModel = beFosViewModel { MatchesViewModel(it.matchRepository) }
    val state by vm.uiState.collectAsState()

    when {
        state.loading -> LoadingState(message = "Загружаем ваши пары")
        state.error != null && state.matches.isEmpty() -> ErrorState(
            message = state.error ?: "Ошибка",
            title = "Не удалось загрузить пары",
            onRetry = vm::load,
        )
        state.matches.isEmpty() -> EmptyState(
            title = "Пар пока нет",
            message = "Когда вы и другой человек поставите друг другу «Нравится», здесь появится пара и чат откроется сам.",
            overline = "Пары",
        )
        else -> LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = Spacing.gutter),
            verticalArrangement = Arrangement.spacedBy(Spacing.md),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(top = Spacing.lg, bottom = 96.dp),
        ) {
            item {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(bottom = Spacing.xs),
                    verticalArrangement = Arrangement.spacedBy(Spacing.xs),
                ) {
                    Text(
                        "ВАШИ ПАРЫ",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Text(
                        "${state.matches.size}",
                        style = MaterialTheme.typography.headlineMedium,
                        color = MaterialTheme.colorScheme.onBackground,
                    )
                }
            }
            items(state.matches, key = { it.matchId }) { match ->
                MatchCard(
                    photoUrl = match.photoUrl,
                    name = "${match.name}, ${match.age}",
                    subtitle = match.lastMessage ?: "Начните общение",
                    compatibility = match.compatibility,
                    unread = match.unread,
                    onClick = { onOpenChat(match.matchId) },
                )
            }
        }
    }
}
