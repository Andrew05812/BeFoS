package app.befos.presentation.plans

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.ListSkeleton
import app.befos.core.designsystem.Spacing
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.Message
import app.befos.presentation.chat.PLAN_KIND_UNKNOWN
import app.befos.presentation.chat.PLAN_KIND_WORDS
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * What the plan went through, in the order the pair went through it.
 *
 * The rows are the conversation's own plan lines, read through the plan rather than through the
 * thread, so this page draws the chat's vocabulary instead of a second one: a pair comparing the two
 * screens finds the same words for the same move, and a move written after this build was frozen
 * arrives here as a line that says it is not readable rather than as a hole in the record.
 */
@Composable
fun PlanHistoryScreen(planId: String, onBack: () -> Unit) {
    val vm: PlanHistoryViewModel = beFosViewModel { PlanHistoryViewModel(it.planRepository, planId) }
    val state by vm.uiState.collectAsState()
    val rows = remember(state.events) { state.events.map { planHistoryRowUi(it) } }
    // The chronology is oldest first, because that is the order the pair lived it, and the reading
    // starts where the arrangement now stands: opening a long history at its top would make the
    // person scroll to find out what their plan currently is.
    val listState = rememberLazyListState()

    Scaffold(topBar = { AppTopBar(title = "История плана", onBack = onBack) }) { padding ->
        when {
            state.loading -> ListSkeleton(Modifier.padding(padding), rows = 4)
            state.error != null && rows.isEmpty() -> ErrorState(
                message = state.error.orEmpty(),
                title = "Не удалось прочитать историю",
                onRetry = vm::load,
                modifier = Modifier.padding(padding),
            )
            rows.isEmpty() -> EmptyState(
                title = "Истории пока нет",
                message = "Строк здесь столько, сколько движений сделал план. Первая появится, когда пара " +
                    "изменит час, место или свой ответ.",
                overline = "История плана",
                actionLabel = "Обновить",
                onAction = vm::load,
                modifier = Modifier.padding(padding),
            )
            else -> LazyColumn(
                state = listState,
                modifier = Modifier
                    .padding(padding)
                    .fillMaxSize()
                    .padding(horizontal = Spacing.gutter),
                verticalArrangement = Arrangement.spacedBy(Spacing.md),
                contentPadding = PaddingValues(vertical = Spacing.lg),
            ) {
                state.error?.let { failure ->
                    item {
                        // The rows below are the last chronology this device read, and the pair may
                        // have moved the plan since. They stay, and they are named as that.
                        InlineNotice(text = failure, actionLabel = "Перечитать", onAction = vm::load)
                    }
                }
                items(rows, key = { it.id }) { row ->
                    HistoryRow(row)
                }
            }
        }
    }

    // One item past the end still lands on the last row, and the count is deliberately not added out
    // by hand: the notice above is the list's own first item only when the read was refused, and a
    // scroll that counted it either way would be one row short half the time.
    LaunchedEffect(rows.size) {
        if (rows.isNotEmpty()) listState.scrollToItem(rows.size)
    }
}

/**
 * One move the plan made, as the pair's record says it.
 *
 * The row answers the four questions a history is opened for: what kind of word this is, whose tap
 * wrote it, when, and what actually moved. The last is left to the server's own sentence, because
 * that is the only place the value a field had *before* the move still exists — the plan row holds
 * only what it holds now, and a screen that reprinted those fields would show the pair their current
 * place and nothing of the one they gave up.
 */
@Composable
private fun HistoryRow(row: PlanHistoryRowUi) {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(Spacing.lg),
            verticalArrangement = Arrangement.spacedBy(Spacing.xs),
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
            ) {
                Box(
                    Modifier
                        .size(8.dp)
                        .clip(CircleShape)
                        .background(
                            if (row.latest) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.outline
                        )
                )
                Text(
                    text = listOfNotNull(row.typeWord, row.moment.ifBlank { null }).joinToString(" · "),
                    style = MaterialTheme.typography.labelMedium,
                    color = if (row.latest) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(
                text = row.sentence,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurface,
            )
            Text(
                // Whose tap wrote the line, and — only for a kind this copy has no word for — the
                // fact that the row cannot name it. The sentence above still stands on its own.
                text = row.who + (row.unknownWord?.let { " · $it" } ?: ""),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * The screen's reading of one journal line, kept apart from the composable so each state a history
 * can hold is checkable against a line the way the server actually writes it — including the kinds
 * this build has never seen, which are exactly the ones a screen built as a `when` over known kinds
 * would drop.
 */
internal data class PlanHistoryRowUi(
    val id: String,
    val typeWord: String,
    val who: String,
    val moment: String,
    val sentence: String,
    val latest: Boolean,
    // Set when the line's kind is one this copy has no word for.
    val unknownWord: String?,
)

internal fun planHistoryRowUi(
    message: Message,
    zone: ZoneId = ZoneId.systemDefault(),
): PlanHistoryRowUi {
    val known = PLAN_KIND_WORDS[message.kind]
    val words = known ?: PLAN_KIND_UNKNOWN
    return PlanHistoryRowUi(
        id = message.id,
        typeWord = words.overline,
        who = if (message.isOwn) "Вы" else "Партнёр",
        moment = historyMoment(message.createdAt, zone),
        sentence = message.body,
        latest = message.plan?.isLatest == true,
        unknownWord = if (known == null) words.current else null,
    )
}

/**
 * When the line was written, in the reader's own calendar, or nothing when the text will not parse.
 *
 * This is the moment of the record, not the moment of the meeting: the pair's hour travels inside the
 * sentence, named in UTC because the two of them are often in two cities, while «when did we change
 * it» is always asked about the reader's own day. An unreadable stamp is left out rather than printed
 * as the server's raw text — a history showing a time nobody can place has stopped being evidence.
 */
private fun historyMoment(iso: String, zone: ZoneId): String {
    val at = runCatching { OffsetDateTime.parse(iso).atZoneSameInstant(zone) }.getOrNull() ?: return ""
    return at.format(DateTimeFormatter.ofPattern("d MMMM, HH:mm", Locale("ru")))
}
