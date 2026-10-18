package app.befos.presentation.moderation

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.window.DialogProperties
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppButtonVariant
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.InterestChip
import app.befos.core.designsystem.ListSkeleton
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.ReportCard
import app.befos.domain.model.ReportReviewRow
import app.befos.presentation.common.ReportReasonLabels
import app.befos.presentation.common.ReportStatusLabels
import app.befos.presentation.common.reportStatusLabel
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ModerationScreen(onBack: () -> Unit) {
    val vm: ModerationViewModel = beFosViewModel { ModerationViewModel(it.moderationRepository) }
    val state by vm.uiState.collectAsState()

    Scaffold(topBar = { AppTopBar(title = "Очередь модерации", onBack = onBack) }) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Spacing.gutter, vertical = Spacing.lg),
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            SectionHeader(
                title = "Очередь",
                subtitle = "Жалобы видны модератору в том порядке, в котором они пришли. " +
                    "Решение записывается вместе с вашей рукой — исправить его потом нельзя, " +
                    "можно только дописать следующее.",
            )

            FlowRow(
                horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                verticalArrangement = Arrangement.spacedBy(Spacing.sm),
            ) {
                InterestChip(
                    label = "Все",
                    selected = state.filter == null,
                    onClick = { vm.setFilter(null) },
                )
                ReportStatusLabels.forEach { (slug, label) ->
                    InterestChip(
                        label = label,
                        selected = state.filter == slug,
                        onClick = { vm.setFilter(slug) },
                    )
                }
            }

            if (state.refreshError != null) {
                InlineNotice(
                    text = state.refreshError!!,
                    actionLabel = "Повторить",
                    onAction = vm::load,
                )
            }
            if (state.detailError != null) {
                InlineNotice(
                    text = state.detailError!!,
                    actionLabel = "Повторить",
                    onAction = { vm.closeDetail() },
                )
            }

            when {
                state.loading -> ListSkeleton()
                state.error != null -> ErrorState(message = state.error!!, onRetry = vm::load)
                state.reports.isEmpty() -> EmptyState(
                    title = if (state.filter == null) "Жалоб нет" else "В этом статусе жалоб нет",
                    message = if (state.filter == null) {
                        "Никто ни на кого не жаловался — или весь разбор уже закрыт."
                    } else {
                        "Ни одна жалоба сейчас не стоит в этом статусе. Смените фильтр, " +
                            "чтобы увидеть остальные."
                    },
                )

                else -> state.reports.forEach { card ->
                    AppCard(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { vm.openDetail(card.id) },
                    ) {
                        Column(
                            modifier = Modifier.fillMaxWidth().padding(Spacing.xl),
                            verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                        ) {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(Spacing.md),
                            ) {
                                Text(
                                    queueAccusedWord(card),
                                    style = MaterialTheme.typography.bodyLarge,
                                    fontWeight = FontWeight.SemiBold,
                                    modifier = Modifier.weight(1f),
                                )
                                InterestChip(label = reportStatusLabel(card.status))
                            }
                            Text(
                                queueFactsWord(card),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Text(
                                queueWitnessWord(card),
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }

            if (state.hasMore && state.reports.isNotEmpty()) {
                AppButton(
                    text = "Показать ещё",
                    onClick = vm::loadMore,
                    loading = state.loadingMore,
                    variant = AppButtonVariant.Tonal,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }

    state.detail?.let { detail ->
        DecisionDialog(
            status = detail.card.status,
            allowed = detail.allowedNextStatuses,
            chosen = state.chosenStatus,
            comment = state.comment,
            deciding = state.deciding,
            error = state.decisionError,
            history = detail.reviews,
            onChoose = vm::chooseStatus,
            onComment = vm::setComment,
            onDecide = vm::decide,
            onDismiss = vm::closeDetail,
        )
    }
}

/**
 * The complaint's own dialog: what it says, who wrote it, how it was decided so far, and the statuses
 * this complaint may still be moved to.
 *
 * The chips are drawn from the answer's `allowedNextStatuses` rather than from the label table, so a
 * complaint that is closed shows no way to move it and the screen cannot offer a tap the write route
 * was always going to refuse.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun DecisionDialog(
    status: String,
    allowed: List<String>,
    chosen: String,
    comment: String,
    deciding: Boolean,
    error: String?,
    history: List<ReportReviewRow>,
    onChoose: (String) -> Unit,
    onComment: (String) -> Unit,
    onDecide: () -> Unit,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = Modifier.imePadding(),
        properties = DialogProperties(decorFitsSystemWindows = false),
        title = { Text("Жалоба · ${reportStatusLabel(status)}") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(Spacing.md),
            ) {
                if (allowed.isEmpty()) {
                    Text(
                        "Эта жалоба закрыта. Открыть её снова нельзя: следующие решения пишет " +
                            "только новая жалоба на ту же анкету.",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                } else {
                    Text(
                        "Куда перевести?",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                        verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                    ) {
                        allowed.forEach { slug ->
                            InterestChip(label = reportStatusLabel(slug), selected = chosen == slug, onClick = { onChoose(slug) })
                        }
                    }
                }
                AppTextField(
                    value = comment,
                    onValueChange = onComment,
                    label = "Запись о решении (обязательна при закрытии)",
                    error = error,
                    singleLine = false,
                    minLines = 2,
                    maxLines = 4,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    if (history.isEmpty()) "Решений по этой жалобе ещё нет." else "История решений",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                history.forEach { row ->
                    Text(
                        reviewRowWord(row),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    row.comment?.let {
                        Text(
                            "«$it»",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        },
        confirmButton = {
            if (allowed.isEmpty()) {
                TextButton(onClick = onDismiss) { Text("Закрыть") }
            } else {
                TextButton(
                    onClick = onDecide,
                    enabled = chosen.isNotBlank() && !deciding,
                    modifier = Modifier.semantics { contentDescription = "Записать решение" },
                ) {
                    Text(if (deciding) "Сохраняем…" else "Принять решение")
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !deciding) { Text("Отмена") }
        },
    )
}

/**
 * Whom the complaint is about, named the way the queue can name it.
 *
 * An erased account has no name left to read and no age to state — the server answers both as nothing
 * — so the row says which of the two it is holding rather than drawing an empty line.
 */
internal fun queueAccusedWord(card: ReportCard): String = when {
    card.reported.isDeleted -> "Анкета удалена"
    else -> card.reported.name ?: "Анкета без имени"
}

/** The reason and whatever the account still answers about itself: «Оскорбления · 24 · Казань». */
internal fun queueFactsWord(card: ReportCard): String {
    val reason = ReportReasonLabels[card.reason] ?: card.reason
    // The age is drawn as a bare number, the way every other card in the app draws it: the screen
    // has no plural table for «год/года/лет», and one invented here would be a second copy of
    // something the rest of the product already says without.
    val identity = listOfNotNull(
        card.reported.age?.toString(),
        card.reported.city?.takeIf { it.isNotBlank() },
    )
    return (listOf(reason) + identity).joinToString(" · ")
}

/**
 * Who wrote the complaint and when, on one line.
 *
 * The name of the person who filed it is read by the moderator and by nobody else in the product —
 * that is what makes the queue a working surface rather than a second inbox — so the row says whose
 * word it is acting on instead of leaving it implied.
 */
internal fun queueWitnessWord(card: ReportCard, zone: ZoneId = ZoneId.systemDefault()): String {
    val day = runCatching {
        OffsetDateTime.parse(card.createdAt)
            .atZoneSameInstant(zone)
            .format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale("ru")))
    }.getOrNull()
    val from = "Жалоба от ${card.reporter.name ?: "аккаунта без имени"}"
    return if (day == null) from else "$from · $day"
}

/** One line of the history: whose hand moved it, from what to what. */
internal fun reviewRowWord(row: ReportReviewRow, zone: ZoneId = ZoneId.systemDefault()): String {
    val day = runCatching {
        OffsetDateTime.parse(row.decidedAt)
            .atZoneSameInstant(zone)
            .format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale("ru")))
    }.getOrNull()
    val move = "${row.moderatorName ?: "Модератор"}: " +
        "${reportStatusLabel(row.fromStatus)} → ${reportStatusLabel(row.toStatus)}"
    return if (day == null) move else "$move · $day"
}
