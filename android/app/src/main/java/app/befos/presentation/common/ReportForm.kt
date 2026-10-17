package app.befos.presentation.common

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.window.DialogProperties
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.Spacing
import app.befos.core.network.ApiResult
import app.befos.domain.repository.SafetyRepository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * How much a person may say about a complaint. The number is the server's own
 * (`details: Field(max_length=1000)` in `api/v1/safety.py`), and clamping it here is what keeps a
 * long account of a bad evening from coming back as a validation error the reader cannot fix.
 */
const val MaxReportDetails: Int = 1000

data class ReportFormState(
    val open: Boolean = false,
    // Captured when the dialog opens, not read when it sends: the deck slides to another card the
    // moment an answer lands, and a complaint written after that would name a person the reader
    // never tapped.
    val targetUserId: String? = null,
    val reason: String = "",
    val details: String = "",
    val error: String? = null,
    val sending: Boolean = false,
    val sent: Boolean = false,
)

/**
 * The complaint form, held once so three screens can reach it.
 *
 * `PublicProfileScreen` owned this state and its dialog down to itself until stage 102, when the
 * deck and a conversation needed the same entry. Duplicating the dialog would have duplicated the
 * part that is not UI — which id the complaint is written about, what happens to a second tap while
 * the first is in flight, what the person is told afterwards — so the form lives here and every
 * screen renders it with the one `ReportDialog` below.
 */
class ReportForm(
    private val safety: SafetyRepository,
    private val scope: CoroutineScope,
) {

    private val _state = MutableStateFlow(ReportFormState())
    val state: StateFlow<ReportFormState> = _state.asStateFlow()

    val sent: Boolean get() = _state.value.sent

    fun open(userId: String) = _state.update {
        ReportFormState(open = true, targetUserId = userId)
    }

    fun close() = _state.update { ReportFormState() }

    fun setReason(slug: String) = _state.update { it.copy(reason = slug, error = null) }

    fun setDetails(value: String) = _state.update {
        it.copy(details = value.take(MaxReportDetails), error = null)
    }

    /**
     * One send per tap. `sending` is checked against the state it is written into rather than
     * against a local copy, so a second tap that arrives while the request is open is dropped
     * instead of asking the server the same question twice — where it would land as a duplicate
     * complaint or a 409 the reader has no way to interpret.
     */
    fun submit() {
        val current = _state.value
        val userId = current.targetUserId ?: return
        if (current.sending) return
        if (!ReportReasonLabels.containsKey(current.reason)) {
            _state.update { it.copy(error = "Выберите причину из списка.") }
            return
        }
        _state.update { it.copy(sending = true, error = null) }
        scope.launch {
            val result = safety.report(
                userId = userId,
                reason = current.reason,
                details = current.details.trim().ifBlank { null },
            )
            when (result) {
                // The complaint is kept as written — the reason and the note stay, and the dialog
                // changes to what happened rather than closing on its own. What it does not say is
                // anything about the review: no status, no queue position, no moderator's note.
                is ApiResult.Success -> _state.update { it.copy(sending = false, sent = true) }
                is ApiResult.Error -> _state.update { it.copy(sending = false, error = result.message) }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ReportDialog(
    state: ReportFormState,
    onReason: (String) -> Unit,
    onDetails: (String) -> Unit,
    onSubmit: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        // The dialog has a text field, so the keyboard belongs to it: without this the
        // «Отправить» row stays where it was and a wide keyboard parks itself on top of
        // the only way to finish the report.
        modifier = Modifier.imePadding(),
        properties = DialogProperties(decorFitsSystemWindows = false),
        title = { Text(if (state.sent) "Жалоба отправлена" else "Пожаловаться") },
        text = {
            if (state.sent) {
                Text(
                    "Она видна модератору в очереди разбора. Статус разбора в приложении не " +
                        "показывается: он ничего не меняет в том, что вы видите.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            } else {
                Column(
                    modifier = Modifier.verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(Spacing.md),
                ) {
                    Text(
                        "Что не так с анкетой?",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                        verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                    ) {
                        ReportReasonLabels.forEach { (slug, label) ->
                            InterestChip(
                                label = label,
                                selected = state.reason == slug,
                                onClick = { onReason(slug) },
                            )
                        }
                    }
                    AppTextField(
                        value = state.details,
                        onValueChange = onDetails,
                        label = "Подробности (необязательно)",
                        error = state.error,
                        singleLine = false,
                        minLines = 2,
                        maxLines = 4,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        },
        confirmButton = {
            if (state.sent) {
                TextButton(onClick = onDismiss) { Text("Закрыть") }
            } else {
                TextButton(onClick = onSubmit, enabled = !state.sending) {
                    Text(if (state.sending) "Отправляем…" else "Отправить")
                }
            }
        },
        dismissButton = {
            if (!state.sent) {
                TextButton(onClick = onDismiss, enabled = !state.sending) { Text("Отмена") }
            }
        },
    )
}
