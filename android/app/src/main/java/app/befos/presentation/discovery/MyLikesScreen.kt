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
import androidx.compose.ui.text.style.TextOverflow
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
            // repeats the tap that failed, which is the one thing the reader is waiting for. The name
            // comes first because the sentence without it is about one of fifty rows and does not say
            // which — the same reason the row's own button is described by the person it belongs to.
            state.withdrawFailed?.let { id ->
                val failed = state.likes.firstOrNull { it.userId == id }
                // «Повторить» на этой отметке — тот же глагол, что и в строке, и он подчиняется тому же
                // правилу: пока что-то на проводе, второго запроса не начинается. Отметка остаётся на
                // экране со своим текстом; слово на ней появляется, когда повторить можно.
                val canRepeat = !state.busy && !state.loading && !state.loadingMore
                item(key = "write-error") {
                    InlineNotice(
                        text = if (failed == null) {
                            state.writeError.orEmpty()
                        } else {
                            "${failed.name}: ${state.writeError.orEmpty()}"
                        },
                        actionLabel = if (canRepeat) "Повторить" else null,
                        onAction = if (canRepeat) {
                            { myLikesWriteRetryTarget(state)?.let(vm::withdraw) }
                        } else {
                            null
                        },
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
                        when (myLikesTail(state)) {
                            MyLikesTail.Loading -> Row(
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

                            MyLikesTail.PageRefused -> InlineNotice(
                                text = "Следующая страница не дошла. ${state.moreError}",
                                actionLabel = "Повторить",
                                onAction = vm::loadMore,
                            )

                            MyLikesTail.MoreAvailable -> InlineNotice(
                                text = "Ваших касаний больше, чем стоит на этом списке. " +
                                    "Догружается само, когда вы доходите до конца.",
                                isError = false,
                                actionLabel = "Показать ещё",
                                onAction = vm::loadMore,
                            )

                            MyLikesTail.WaitingForReread -> InlineNotice(
                                text = "Ваших касаний больше, чем стоит на этом списке. Перечитайте его, " +
                                    "и обход пойдёт дальше.",
                                isError = false,
                                actionLabel = "Повторить",
                                onAction = vm::load,
                            )

                            MyLikesTail.End -> Text(
                                "Дальше ваших касаний нет.",
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )

                            MyLikesTail.Nothing -> Unit
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
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(Spacing.lg),
            verticalArrangement = Arrangement.spacedBy(Spacing.xs),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
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
            // The percent the tap carried, on the card's own full measure rather than squeezed between the
            // avatar and the withdraw button. In the narrow slot the phrase was longer than the line and
            // the text system had only one way out: it broke inside the word «Совместимость», which is a
            // thing a person has to be able to read. Here the line is never wrapped — [softWrap] off and one
            // line — so there is no break inside a word to read, and the measure is wide enough that the
            // whole phrase sits on it at the smallest phone and the largest text (see [myLikesScoreFits]).
            Text(
                myLikesScoreWord(like),
                style = MaterialTheme.typography.labelMedium.tabularDigits(),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                softWrap = false,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.fillMaxWidth(),
            )
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
    // Страница без строк и со ссылкой вперёд — это не аккаунт, который никого не лайкал. Половину
    // правила показа сервер решает по присоединённым таблицам, и строка может уйти из вида, оставив
    // за экраном дверь: «Вы пока никого не лайкали» здесь было бы рассказом про человека, а ответ
    // знает только про эту страницу.
    state.truncated || state.nextCursor != null -> MyLikesBody.Rows
    else -> MyLikesBody.Empty
}

/**
 * Whose tap the notice's «Повторить» sends again, or nothing when there is no refused gesture to repeat.
 *
 * The notice and its verb live in a composable, and a composable cannot be asserted on from a JVM test;
 * the choice of target can, and it is the part that was wrong before. A notice that re-reads the list
 * answers a refused write with a page; a notice that repeats the first row's owner withdraws a tap the
 * reader never refused. Both are one line of wiring, and this is where that line lives.
 */
internal fun myLikesWriteRetryTarget(state: MyLikesUiState): String? =
    if (state.writeError == null) null else state.withdrawFailed

/** Which of the sentences below the list the tail of the walk draws. */
internal enum class MyLikesTail {
    Loading, PageRefused, MoreAvailable, WaitingForReread, End, Nothing,
}

/**
 * The tail is this screen's claim about what stands beyond the rows it holds, so its branches resolve in
 * one place and are tested there rather than in the order a `when` happens to be written in.
 *
 * Two rules hold it together. A verb appears only where the key it needs is on the screen: «Повторить»
 * over a refused page and «Показать ещё» over a list that goes on both go through [loadMore], and
 * [MyLikesUiState.nextCursor] is the only thing that verb can ask with. And the sentence that ends the
 * walk belongs to the server, not to an absent key: it is drawn once the last answer said nothing stands
 * beyond these rows.
 *
 * [WaitingForReread] is the branch this screen did not have. A reload that failed drops the key to the
 * rest of the list — the rows above are the earlier read and they stay — while the last answer that did
 * come said more taps stand behind them. Without the branch the tail fell through to [End] and promised
 * a reader the end of a history they had not finished reading, and with a page refusal still in the state
 * it offered «Повторить» pointed at a page whose link had just been thrown away. Its verb is the reload
 * itself, which is the one thing that can hand the walk a key again.
 */
internal fun myLikesTail(state: MyLikesUiState): MyLikesTail = when {
    state.loadingMore -> MyLikesTail.Loading
    state.moreError != null && state.nextCursor != null -> MyLikesTail.PageRefused
    state.truncated && state.nextCursor != null -> MyLikesTail.MoreAvailable
    state.truncated -> MyLikesTail.WaitingForReread
    state.pages > 1 -> MyLikesTail.End
    else -> MyLikesTail.Nothing
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

/**
 * The measure the score line is drawn at: the card's interior, undivided.
 *
 * `Spacing.gutter` on both sides of the screen and `Spacing.lg` on both sides of the card — the same two
 * numbers the row itself is padded with, written out because a JVM test cannot ask a layout pass. What the
 * line used to get instead was this measure minus the avatar, the row's two gaps and the withdraw button:
 * narrower than one word of the phrase, which is why that word was broken in half.
 */
internal fun myLikesScoreSlotDp(screenWidthDp: Float): Float =
    (screenWidthDp - 2f * 20f - 2f * 16f).coerceAtLeast(0f)

/**
 * How wide the widest thing in [text] has to be, in dp, at [textScale].
 *
 * Measured on the longest word rather than on the whole phrase, because a word is the unit the text system
 * cannot move to the next line: given a slot narrower than one word it breaks inside it, and that is
 * precisely what happened here. The estimate is deliberately generous — `labelMedium` is the Overline style
 * ([app.befos.core.designsystem.BeFosTypography]), 11sp carried by 1.4sp of letter spacing, and Cyrillic
 * advance is taken at 0.62em, above what the font actually needs for these letters — so a line this says
 * fits has room left, and one it says does not was never going to.
 */
internal fun myLikesWordWidthDp(text: String, textScale: Float, sizeSp: Float = 11f): Float {
    val longest = text.split(' ').maxOfOrNull { it.length } ?: 0
    return longest * (0.62f * sizeSp + 1.4f) * textScale
}

/** Whether the score line is drawn on one unbroken line at this screen width and text scale. */
internal fun myLikesScoreFits(like: OutgoingLike, screenWidthDp: Float, textScale: Float): Boolean =
    myLikesWordWidthDp(myLikesScoreWord(like), textScale) <= myLikesScoreSlotDp(screenWidthDp)
