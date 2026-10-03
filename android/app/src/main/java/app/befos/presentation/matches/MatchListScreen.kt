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
import androidx.lifecycle.compose.LifecycleResumeEffect
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.ListSkeleton
import app.befos.core.designsystem.MatchCard
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.tabularDigits
import app.befos.core.di.beFosViewModel

@Composable
fun MatchListScreen(onOpenChat: (String) -> Unit, onGoDiscover: () -> Unit) {
    val vm: MatchesViewModel = beFosViewModel { MatchesViewModel(it.matchRepository) }
    val state by vm.uiState.collectAsState()

    LifecycleResumeEffect(Unit) {
        vm.refreshSilently()
        onPauseOrDispose { }
    }

    when {
        state.loading -> ListSkeleton(rows = 4)
        state.error != null && state.matches.isEmpty() -> ErrorState(
            message = state.error ?: "Проверьте подключение и попробуйте ещё раз.",
            title = "Не удалось загрузить пары",
            onRetry = vm::load,
        )
        state.matches.isEmpty() -> EmptyState(
            title = "Пар пока нет",
            message = "Пара появится здесь, когда вы и другой человек поставите друг другу «Нравится». Тогда вы сможете написать первым.",
            overline = "Пары",
            // An empty list explains the mechanic; the CTA is what the user can do now.
            actionLabel = "Смотреть анкеты",
            onAction = onGoDiscover,
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
                        text = "${state.matches.size}",
                        style = MaterialTheme.typography.headlineMedium.tabularDigits(),
                        color = MaterialTheme.colorScheme.onBackground,
                    )
                }
            }
            items(state.matches, key = { it.matchId }) { match ->
                MatchCard(
                    photoUrl = match.photoUrl,
                    name = "${match.name}, ${match.age}",
                    subtitle = match.lastMessage ?: "Напишите первым",
                    compatibility = match.compatibility,
                    unread = match.unread,
                    onClick = { onOpenChat(match.matchId) },
                )
            }
        }
    }
}
