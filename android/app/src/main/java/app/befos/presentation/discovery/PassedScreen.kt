package app.befos.presentation.discovery

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalDensity
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
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.AppCard
import app.befos.core.designsystem.AppTopBar
import app.befos.core.designsystem.Avatar
import app.befos.core.designsystem.EmptyState
import app.befos.core.designsystem.ErrorState
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.ListSkeleton
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.PassedUser
import app.befos.presentation.common.PageTailRow
import app.befos.presentation.common.PageTailWords
import app.befos.presentation.common.pageTail
import app.befos.presentation.common.passedEntryWord
import app.befos.presentation.common.shownWord
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Whom this account dismissed, read from the rows those swipes wrote, with the one verb that takes an
 * answer back.
 *
 * The deck only ever spoke of a pass by silence — the person simply stopped coming — so this page
 * draws the vocabulary the deck and the inbox already use and puts its action on the row itself: a
 * visible word, not a gesture hidden behind a control.
 */
@Composable
fun PassedScreen(onBack: () -> Unit, onOpenProfile: (String) -> Unit) {
    val vm: PassedViewModel = beFosViewModel { PassedViewModel(it.discoveryRepository) }
    val state by vm.uiState.collectAsState()
    val scrollState = rememberScrollState()

    // Reaching the end of what the screen holds is the reader asking for the rest; the gate closes
    // while a page is on the wire, so the ask cannot fire twice. A list short enough not to overflow
    // has already reached its end, so it asks too, and stops once the rows are taller than the screen.
    val prefetchPx = with(LocalDensity.current) { 160.dp.toPx() }.toInt()
    val shouldAskForMore by remember(prefetchPx) {
        derivedStateOf {
            state.canLoadMore &&
                (scrollState.maxValue - scrollState.value <= prefetchPx || scrollState.maxValue == 0)
        }
    }
    LaunchedEffect(shouldAskForMore) {
        if (shouldAskForMore) vm.loadMore()
    }

    Scaffold(topBar = { AppTopBar(title = passedEntryWord(), onBack = onBack) }) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(scrollState)
                .padding(horizontal = Spacing.gutter, vertical = Spacing.lg),
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            SectionHeader(
                title = passedEntryWord(),
                subtitle = "Список читается из строк пропуска, а не из колоды: возвращённая анкета " +
                    "встанет в подбор, когда колода доберёт следующие карточки.",
            )

            // The row is gone from this page the moment the write lands, so the notice has to say who
            // it was about and what the release did not do — bring the person back to the front.
            state.released?.let { name ->
                InlineNotice(
                    text = "$name больше не пропущен. В подбор он вернётся при следующем доборе " +
                        "анкет, а не в эту полосу карточек.",
                    isError = false,
                    actionLabel = "Скрыть",
                    onAction = vm::dismissReleased,
                )
            }
            // How far the walk has come, in the reader's own words: the rows the device actually holds,
            // and never a total the server did not name.
            if (!state.loading && state.passed.isNotEmpty()) {
                Text(
                    passedShownWord(state.passed.size, state.truncated),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (state.error != null && state.passed.isNotEmpty()) {
                InlineNotice(
                    text = state.error!!,
                    actionLabel = "Повторить",
                    onAction = vm::load,
                )
            }

            when {
                state.loading -> ListSkeleton()
                state.error != null -> ErrorState(
                    title = "Не удалось прочитать пропуски",
                    message = state.error!!,
                    onRetry = vm::load,
                )
                state.passed.isEmpty() -> EmptyState(
                    title = "Вы пока никого не пропускали",
                    message = "Здесь появятся те, кого вы убрали свайпом. Ответ можно забрать — " +
                        "анкета снова встанет в подбор.",
                    actionLabel = "Обновить",
                    onAction = vm::load,
                )

                else -> state.passed.forEach { user ->
                    AppCard(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { onOpenProfile(user.userId) },
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(Spacing.lg),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(Spacing.md),
                        ) {
                            Avatar(url = user.photoUrl, size = 44.dp, initials = user.name)
                            Column(
                                modifier = Modifier.weight(1f),
                                verticalArrangement = Arrangement.spacedBy(2.dp),
                            ) {
                                Text(
                                    user.name,
                                    style = MaterialTheme.typography.bodyLarge,
                                    fontWeight = FontWeight.SemiBold,
                                )
                                Text(
                                    passedRowWord(user),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                            TextButton(
                                onClick = { vm.release(user.userId) },
                                enabled = !state.busy,
                                // The name sits in the sibling column, so the tap alone would read as
                                // «Вернуть в подбор» with nobody it belongs to.
                                modifier = Modifier.semantics { contentDescription = "Вернуть в подбор для ${user.name}" },
                            ) {
                                Text("Вернуть в подбор")
                            }
                        }
                    }
                }
            }

            // What stands beyond these rows, and the one verb that reaches it.
            if (!state.loading && state.error == null) {
                PageTailRow(
                    tail = pageTail(state.walk()),
                    moreError = state.moreError,
                    words = PASSED_TAIL_WORDS,
                    onRepeat = vm::retryMore,
                    onReread = vm::load,
                )
            }
        }
    }
}

private val PASSED_TAIL_WORDS = PageTailWords(
    loading = "Догружаю ваши пропуски…",
    moreAvailable = "Пропущенных больше, чем стоит на этом списке. " +
        "Догружается само, когда вы доходите до конца.",
    waitingForReread = "Пропущенных больше, чем стоит на этом списке. Перечитайте его, " +
        "и обход пойдёт дальше.",
    end = "Дальше ваших пропусков нет.",
)

/**
 * How far the walk has come: the rows on the screen, and whether the list goes on past them.
 */
internal fun passedShownWord(shown: Int, truncated: Boolean): String =
    shownWord(shown, truncated, "пропуск", "пропуска", "пропусков")

/**
 * The row's second line: who this person is, and the day the card was swiped past.
 *
 * The day comes off the server's own moment and is dropped rather than guessed when that text cannot
 * be read as one — a list about the account's own answers has no business inventing one of them.
 */
internal fun passedRowWord(user: PassedUser, zone: ZoneId = ZoneId.systemDefault()): String {
    val identity = "${user.age} · ${user.city}"
    val day = runCatching {
        OffsetDateTime.parse(user.passedAt)
            .atZoneSameInstant(zone)
            .format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale("ru")))
    }.getOrNull() ?: return identity
    return "$identity · $day"
}
