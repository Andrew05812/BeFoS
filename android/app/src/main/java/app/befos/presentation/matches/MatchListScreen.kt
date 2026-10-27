package app.befos.presentation.matches

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.ListSkeleton
import app.befos.core.designsystem.MatchCard
import app.befos.core.designsystem.Motion
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.tabularDigits
import app.befos.core.di.beFosViewModel

@Composable
fun MatchListScreen(
    onOpenChat: (String) -> Unit,
    // The pair's own reading, opened from the row that already names the pair. The card's tap stays the
    // thread it always was: a list a person has learned to tap cannot silently change what a tap means.
    onOpenPairProfile: (String) -> Unit,
    onGoDiscover: () -> Unit,
) {
    val vm: MatchesViewModel = beFosViewModel { MatchesViewModel(it.matchRepository) }
    val state by vm.uiState.collectAsState()

    LifecycleResumeEffect(Unit) {
        vm.refreshSilently()
        onPauseOrDispose { }
    }

    // The answer says its own piece and then steps aside; leaving it glued to the header would
    // let yesterday's «пара убрана» read as news about a pair from today's list.
    LaunchedEffect(state.dissolveNotice) {
        if (state.dissolveNotice != null) {
            kotlinx.coroutines.delay(Motion.Notice.toLong())
            vm.clearDissolveNotice()
        }
    }

    state.confirmDissolve?.let { match ->
        AlertDialog(
            onDismissRequest = vm::cancelDissolve,
            title = { Text("Убрать пару с ${match.name}?") },
            // The part a person is likely to expect to be kept, and the part that is a promise:
            // the conversation and the plans end with the pair, and no block is placed for it.
            text = {
                Text(
                    "Переписка и общие планы удалятся и не вернутся. " +
                        "Анкета человека при этом остаётся открытой: убрать пару — не значит заблокировать. " +
                        "Начать заново можно будет только вдвоём — если «Нравится» поставите вы оба."
                )
            },
            confirmButton = {
                TextButton(onClick = vm::confirmDissolve) {
                    Text("Убрать пару", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = { TextButton(onClick = vm::cancelDissolve) { Text("Отмена") } },
        )
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
                    // The list is still on screen, so nothing failed loudly. Without this line
                    // a pair that arrived while the refresh was down reads as a pair that
                    // never existed.
                    state.refreshError?.let {
                        InlineNotice(it, actionLabel = "Повторить", onAction = vm::refreshSilently)
                    }
                    state.dissolveNotice?.let {
                        InlineNotice(it, isError = state.dissolveNoticeIsError)
                    }
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
                    onOpenPairProfile = { onOpenPairProfile(match.matchId) },
                    onDissolve = { vm.askDissolve(match) },
                )
            }
        }
    }
}
