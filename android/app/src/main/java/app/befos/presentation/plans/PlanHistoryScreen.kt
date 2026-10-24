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
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTextField
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
 * What the plan went through, in the order the pair went through it, and the word only this person
 * keeps about it.
 *
 * The rows are the conversation's own plan lines, read through the plan rather than through the
 * thread, so this page draws the chat's vocabulary instead of a second one: a pair comparing the two
 * screens finds the same words for the same move, and a move written after this build was frozen
 * arrives here as a line that says it is not readable rather than as a hole in the record.
 *
 * The remark sits above them and is not one of them. It is the plan's own page holding the one field
 * the pair does not share, and it stays on screen even when the chronology is empty — a plan the pair
 * has not yet moved is exactly the plan a person wants to leave themselves a line about.
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
    // Every row the page puts before the chronology moves the reading position: the private remark is
    // one item, a refused refresh is another, and a plan nobody has moved yet carries its own notice.
    val headerRows = 1 + (if (state.error != null) 1 else 0) + (if (rows.isEmpty()) 1 else 0)

    Scaffold(topBar = { AppTopBar(title = "История плана", onBack = onBack) }) { padding ->
        when {
            state.loading -> ListSkeleton(Modifier.padding(padding), rows = 4)
            state.error != null && rows.isEmpty() -> ErrorState(
                message = state.error.orEmpty(),
                title = "Не удалось прочитать историю",
                onRetry = vm::load,
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
                item {
                    NoteCard(
                        note = state.myNote,
                        busy = state.noteBusy,
                        error = state.noteError,
                        onSave = vm::saveNote,
                    )
                }
                if (rows.isEmpty()) {
                    item {
                        // Not an error and not an empty screen: a plan the pair has not moved yet has
                        // nothing to report, and the person came here for their own line about it.
                        AppCard(modifier = Modifier.fillMaxWidth()) {
                            Column(
                                modifier = Modifier.padding(Spacing.lg),
                                verticalArrangement = Arrangement.spacedBy(Spacing.xs),
                            ) {
                                Text(
                                    "ИСТОРИИ ПОКА НЕТ",
                                    style = MaterialTheme.typography.labelMedium,
                                    fontWeight = FontWeight.Bold,
                                    color = MaterialTheme.colorScheme.onSurface,
                                )
                                Text(
                                    "Строк здесь столько, сколько движений сделал план. Первая появится, " +
                                        "когда пара изменит час, место или свой ответ.",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
                items(rows, key = { it.id }) { row ->
                    HistoryRow(row)
                }
            }
        }
    }

    // One item past the end still lands on the last row, and the count is not added out by hand at the
    // call site: the notices above are the list's own items only when their read failed or the plan
    // has no lines yet, so `headerRows` is what says where the chronology actually begins.
    LaunchedEffect(rows.size, headerRows) {
        if (rows.isNotEmpty()) listState.scrollToItem(headerRows + rows.size)
    }
}

/**
 * The person's own line about their own plan: printed, editable, and erasable from one card.
 *
 * The field starts from what the server holds, so an emptied one is a decision to take the word back
 * rather than a blank nobody meant, and a save that moved nothing sends no request at all. Both the
 * opened editor and the text inside it are kept across a recreation of the screen: a person who typed
 * a reminder and turned the phone lost both the sentence and the reason they wrote it if either were
 * plain composition state.
 */
@Composable
private fun NoteCard(
    note: String?,
    busy: Boolean,
    error: String?,
    onSave: (String) -> Unit,
) {
    var open by rememberSaveable { mutableStateOf(false) }
    var draft by rememberSaveable { mutableStateOf(note.orEmpty()) }
    var sent by rememberSaveable { mutableStateOf(false) }
    val stored = note.orEmpty().trim()
    val limit = planNoteOverfall(draft)
    // The editor closes when the word the server holds catches up with what was typed — «сохранено»
    // says the reloaded row rather than a flag this screen invented — and a refusal leaves the typed
    // text where it was, because losing a word the server would not take is the worse ending.
    LaunchedEffect(sent, busy, draft, note) {
        if (sent && !busy && draft.trim() == stored) {
            sent = false
            open = false
        }
    }

    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(Spacing.lg),
            verticalArrangement = Arrangement.spacedBy(Spacing.xs),
        ) {
            Text(
                PLAN_NOTE_OVERLINE,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (!open) {
                Text(
                    planNoteWord(note),
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                Text(
                    PLAN_NOTE_PRIVATE_WORD,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                AppButton(
                    text = if (stored.isEmpty()) PLAN_NOTE_EDIT_WORD else "Изменить своё слово",
                    onClick = {
                        draft = stored
                        sent = false
                        open = true
                    },
                    enabled = !busy,
                    variant = AppButtonVariant.Ghost,
                    modifier = Modifier.fillMaxWidth(),
                )
                if (stored.isNotEmpty()) {
                    TextButton(onClick = { onSave("") }, enabled = !busy) {
                        Text(
                            PLAN_NOTE_CLEAR_WORD,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            } else {
                AppTextField(
                    value = draft,
                    onValueChange = { draft = it },
                    label = "Моё слово об этой встрече",
                    placeholder = "Например, взять билеты и подъезд с торца",
                    singleLine = false,
                    minLines = 2,
                    maxLines = 4,
                    error = limit,
                    modifier = Modifier.fillMaxWidth(),
                )
                if (limit != null) {
                    Text(
                        limit,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                } else {
                    Text(
                        PLAN_NOTE_PRIVATE_WORD,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                AppButton(
                    text = if (planNoteEdit(note, draft).change == PlanNoteChange.CLEAR)
                        PLAN_NOTE_CLEAR_WORD else PLAN_NOTE_SAVE_WORD,
                    onClick = {
                        sent = true
                        onSave(draft)
                    },
                    enabled = !busy && canSavePlanNote(note, draft),
                    variant = AppButtonVariant.Tonal,
                    modifier = Modifier.fillMaxWidth(),
                )
                TextButton(
                    onClick = {
                        draft = stored
                        open = false
                    },
                    enabled = !busy,
                ) {
                    Text(
                        "Отмена",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            error?.let {
                InlineNotice(text = it, actionLabel = "Повторить", onAction = { onSave(draft) })
            }
        }
    }
}

/** One move the plan made, as the pair's record says it. */
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
