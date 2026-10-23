package app.befos.presentation.discovery

import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
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
import app.befos.core.designsystem.rememberHaptics
import app.befos.core.designsystem.tabularDigits
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.OutgoingLike
import app.befos.presentation.common.myLikesEntryWord
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Whom this account tapped, read from the rows those taps wrote, one page at a time, with the one verb
 * that takes a tap back.
 *
 * The account could already read both other halves of its social life — who came to it, and who it
 * dismissed — while its own hearts stayed a write with no read. This page draws the vocabulary the inbox
 * and the pass list already use and puts its action on the row itself: a visible word, not a gesture
 * hidden behind a control.
 *
 * The list is a walk now, not a snapshot of fifty. The rows are keyed by person, so a card that stays
 * between two pages keeps its place and its own state instead of being recomposed as somebody else's,
 * and the page behind them arrives when the reader reaches the end — or by the word on the notice, for
 * a list short enough that it never has to scroll.
 */
@Composable
fun MyLikesScreen(onBack: () -> Unit, onOpenProfile: (String) -> Unit) {
    val vm: MyLikesViewModel = beFosViewModel { MyLikesViewModel(it.discoveryRepository) }
    val state by vm.uiState.collectAsState()
    val listState = rememberLazyListState()
    val haptics = rememberHaptics()

    // Reaching the end of what is on the screen is the reader asking for the rest. The trigger sits
    // three rows from the bottom so the next page is usually in by the time the thumb stops, and it
    // cannot fire twice: `canLoadMore` is false while a page is on the wire.
    val shouldAskForMore by remember {
        derivedStateOf {
            val info = listState.layoutInfo
            val lastVisible = info.visibleItemsInfo.lastOrNull()?.index ?: -1
            state.canLoadMore && info.totalItemsCount > 0 && lastVisible >= info.totalItemsCount - 3
        }
    }
    LaunchedEffect(shouldAskForMore) {
        if (shouldAskForMore) vm.loadMore()
    }

    Scaffold(topBar = { AppTopBar(title = myLikesEntryWord(), onBack = onBack) }) { padding ->
        LazyColumn(
            state = listState,
            modifier = Modifier
                .padding(padding)
                .fillMaxSize(),
            contentPadding = PaddingValues(
                start = Spacing.gutter,
                end = Spacing.gutter,
                top = Spacing.lg,
                bottom = Spacing.xxl,
            ),
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            item(key = "header") {
                SectionHeader(
                    title = myLikesEntryWord(),
                    subtitle = "Процент на строке читается из записи лайка, а не считается заново: " +
                        "это тот процент, который стоял на карточке в минуту вашего касания.",
                )
            }

            // The row is gone from this page the moment the write lands, so the notice has to say whose
            // tap it withdrew and what the withdrawal deliberately did not do — end a pair.
            state.withdrawn?.let { name ->
                item(key = "withdrawn") {
                    InlineNotice(
                        text = "$name больше не лайкнут. Если к этому моменту пара уже сложилась, она " +
                            "остаётся — убрать её можно на экране пар.",
                        isError = false,
                        actionLabel = "Скрыть",
                        onAction = vm::dismissWithdrawn,
                    )
                }
            }

            // A page that stopped says how far it got. The old line admitted the rest existed and
            // confessed the screen could not reach them; the cursor took the second half away, and what
            // is left to tell is the count this walk has gathered.
            if (!state.loading && state.likes.isNotEmpty()) {
                item(key = "count") {
                    Text(
                        text = myLikesShownWord(state.likes.size, state.truncated),
                        style = MaterialTheme.typography.labelMedium.tabularDigits(),
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            if (state.error != null && state.likes.isNotEmpty()) {
                item(key = "read-error") {
                    InlineNotice(
                        text = state.error!!,
                        actionLabel = "Повторить",
                        onAction = vm::load,
                    )
                }
            }

            // A gesture the server refused, named by the row it belongs to. The list under it is the
            // account's own read and it did not go anywhere, so this notice carries no reload: its verb
            // repeats the tap that failed, which is the one thing the reader is waiting for.
            state.withdrawFailed?.let { id ->
                val failed = state.likes.firstOrNull { it.userId == id }
                item(key = "write-error") {
                    InlineNotice(
                        text = state.writeError.orEmpty() + (
                            failed?.let { " — ${it.name} остаётся в списке." } ?: ""
                            ),
                        actionLabel = "Повторить",
                        onAction = { vm.withdraw(id) },
                    )
                }
            }

            when (myLikesBody(state)) {
                MyLikesBody.Skeleton -> item(key = "skeleton") { ListSkeleton() }

                MyLikesBody.ReadFailure -> item(key = "read-failure") {
                    ErrorState(
                        title = "Не удалось прочитать ваши лайки",
                        message = state.error!!,
                        onRetry = vm::load,
                    )
                }

                MyLikesBody.Empty -> item(key = "empty") {
                    EmptyState(
                        title = "Вы пока никого не лайкали",
                        message = "Здесь появятся те, кого вы выбрали сердцем. Отзыв лайка не распускает " +
                            "готовую пару и не трогает чужой ответ — только ваше касание.",
                        actionLabel = "Обновить",
                        onAction = vm::load,
                    )
                }

                MyLikesBody.Rows -> {
                    items(state.likes, key = { it.userId }) { like ->
                        MyLikeRow(
                            like = like,
                            // Only the row that is on the wire loses its verb: the others stay readable,
                            // and a list that went grey row by row would look like the whole history had
                            // been refused. While a page is out the verbs wait with it — a tap taken back
                            // under a page still on the wire would be answered by two redraws of one list.
                            inFlight = state.withdrawing == like.userId,
                            blocked = state.busy || state.loadingMore,
                            onOpenProfile = { onOpenProfile(like.userId) },
                            onWithdraw = {
                                haptics.medium()
                                vm.withdraw(like.userId)
                            },
                        )
                    }

                    // The tail of the walk: what is happening now, what failed, or the sentence that ends
                    // it. Nothing here is a button the reader has to notice to keep reading — the list
                    // comes by itself — but a page that failed has to be repeatable by a tap.
                    item(key = "tail") {
                        when {
                            state.loadingMore -> Row(
                                modifier = Modifier.fillMaxWidth().padding(vertical = Spacing.sm),
                                horizontalArrangement = Arrangement.spacedBy(Spacing.md, Alignment.CenterHorizontally),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                CircularProgressIndicator(modifier = Modifier.size(22.dp), strokeWidth = 2.5.dp)
                                Text(
                                    "Догружаю ваши касания…",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }

                            state.moreError != null -> InlineNotice(
                                text = "Следующая страница не дошла. ${state.moreError}",
                                actionLabel = "Повторить",
                                onAction = vm::loadMore,
                            )

                            state.truncated -> InlineNotice(
                                text = "Ваших касаний больше, чем стоит на этом списке. " +
                                    "Догружается само, когда вы доходите до конца.",
                                isError = false,
                                actionLabel = "Показать ещё",
                                onAction = vm::loadMore,
                            )

                            state.pages > 1 -> Text(
                                "Дальше ваших касаний нет.",
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                }
            }
        }
    }
}

/**
 * One tap the account made: the person, the day, the percent the card carried, and the verb that takes
 * the gesture back.
 */
@Composable
private fun MyLikeRow(
    like: OutgoingLike,
    inFlight: Boolean,
    blocked: Boolean,
    onOpenProfile: () -> Unit,
    onWithdraw: () -> Unit,
) {
    AppCard(
        modifier = Modifier.fillMaxWidth(),
        onClick = onOpenProfile,
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(Spacing.lg),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(Spacing.md),
        ) {
            Avatar(url = like.photoUrl, size = 44.dp, initials = like.name)
            Column(
                modifier = Modifier.weight(1f),
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Text(
                    like.name,
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    myLikesRowWord(like),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    myLikesScoreWord(like),
                    style = MaterialTheme.typography.labelMedium.tabularDigits(),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            TextButton(
                onClick = onWithdraw,
                enabled = !blocked,
                // The name sits in the sibling column, so the tap alone would read as
                // «Забрать лайк» with nobody it belongs to. While the write is out the word says so —
                // a button that stays lit and answers nothing looks like a tap the app refused.
                modifier = Modifier.semantics {
                    contentDescription = if (inFlight) {
                        "Отзываю лайк для ${like.name}"
                    } else {
                        "Забрать лайк для ${like.name}"
                    }
                },
            ) {
                Text(if (inFlight) "Отзываю…" else "Забрать лайк")
            }
        }
    }
}

/** Which of the four bodies the area under the notices draws. */
internal enum class MyLikesBody { Skeleton, ReadFailure, Empty, Rows }

/**
 * The rows the account holds outrank a failure to read more of them.
 *
 * Four states want the same space: the first page still on the wire, a read that did not come, a list
 * the server says is empty, and the list itself. The order they are resolved in is the screen's whole
 * claim about history, so it is written down once and tested rather than left to the branch order of a
 * `when` inside a LazyColumn — which is how stage 123 found it: a refused withdrawal set the read error,
 * and the card «Не удалось прочитать ваши лайки» replaced rows the server had just finished answering.
 *
 * Empty is a fact about the account, and it is only ever drawn when the read came back: a timeout with
 * nothing on the screen is a failure, not a confession that nobody has been liked. A failure with rows
 * on the screen is the other half of the same rule — the notice above them names which read did not
 * arrive, and the history the device holds stays where the reader left it.
 */
internal fun myLikesBody(state: MyLikesUiState): MyLikesBody = when {
    state.loading -> MyLikesBody.Skeleton
    state.likes.isNotEmpty() -> MyLikesBody.Rows
    state.error != null -> MyLikesBody.ReadFailure
    else -> MyLikesBody.Empty
}

/**
 * How far the walk has come, in the reader's own words: the rows on the screen, and whether the list
 * goes on past them.
 *
 * The count is what the device actually holds — never a total the server did not name. A page knows how
 * many taps it read and nothing about how many the account made, and «из N» would be a number about
 * nothing.
 */
internal fun myLikesShownWord(shown: Int, truncated: Boolean): String =
    if (truncated) "Показано $shown касаний, и список идёт дальше" else "Показано $shown касаний — весь список"

/**
 * The row's second line: who this person is, and the day this account reached for them.
 *
 * The day comes off the server's own moment and is dropped rather than guessed when that text cannot
 * be read as one — a list about the account's own answers has no business inventing one of them.
 */
internal fun myLikesRowWord(like: OutgoingLike, zone: ZoneId = ZoneId.systemDefault()): String {
    val identity = "${like.age} · ${like.city}"
    val day = runCatching {
        OffsetDateTime.parse(like.likedAt)
            .atZoneSameInstant(zone)
            .format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale("ru")))
    }.getOrNull() ?: return identity
    return "$identity · $day"
}

/**
 * The row's third line: the percent the account was shown when it made the tap, or the sentence that
 * says none is written.
 *
 * A missing percent is not zero: the row was written before percents were stored on likes, and
 * inventing one would put a number on a decision the reader made without seeing it.
 */
internal fun myLikesScoreWord(like: OutgoingLike): String =
    like.compatibility?.let { "Совместимость $it%" } ?: "Процент не записан"
