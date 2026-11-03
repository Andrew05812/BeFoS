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
import app.befos.core.designsystem.MatchMoment
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.tabularDigits
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.IncomingLike
import app.befos.presentation.common.PageTailRow
import app.befos.presentation.common.PAGE_PREFETCH_PX_DP
import app.befos.presentation.common.namedVerbOnRow
import app.befos.presentation.common.shouldAskForMoreByPixels
import app.befos.presentation.common.PageTailWords
import app.befos.presentation.common.likedMeEntryWord
import app.befos.presentation.common.pageTail
import app.befos.presentation.common.shownWord
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Who tapped this account, read from the rows those taps wrote.
 *
 * The deck only ever showed the person going the other way, so this page draws the same vocabulary
 * the deck and the block list already use — an avatar, one line of identity, one line of the
 * server's own text — and keeps the answer it offers on the route the deck already writes, so a
 * like given here is the like the pair's history would have held anyway.
 */
@Composable
fun LikedMeScreen(onBack: () -> Unit, onOpenProfile: (String) -> Unit, onOpenMatch: (String) -> Unit) {
    val vm: LikedMeViewModel = beFosViewModel {
        LikedMeViewModel(it.discoveryRepository, it.answeredUsers)
    }
    val state by vm.uiState.collectAsState()
    val scrollState = rememberScrollState()

    // Reaching the end of what the screen holds is the reader asking for the rest. The trigger sits
    // one screen-height-short-of the bottom, so the next page is usually in by the time the thumb
    // stops, and it cannot fire twice: `canLoadMore` is false while a page is on the wire. A list that
    // does not even overflow the screen has already reached its end, so it asks too — and stops asking
    // as soon as the rows are taller than the viewport.
    val prefetchPx = with(LocalDensity.current) { PAGE_PREFETCH_PX_DP.dp.toPx() }.toInt()
    val shouldAskForMore by remember(prefetchPx) {
        derivedStateOf {
            shouldAskForMoreByPixels(
                canLoadMore = state.canLoadMore,
                maxScroll = scrollState.maxValue,
                scroll = scrollState.value,
                prefetchPx = prefetchPx,
            )
        }
    }
    LaunchedEffect(shouldAskForMore) {
        if (shouldAskForMore) vm.loadMore()
    }

    state.match?.let { match ->
        MatchMoment(
            name = match.name,
            photoUrl = match.photoUrl,
            compatibility = match.compatibility,
            onOpenChat = {
                vm.dismissMatch()
                onOpenMatch(match.matchId)
            },
            onDismiss = vm::dismissMatch,
            secondaryLabel = "К списку лайков",
        )
    }

    Scaffold(topBar = { AppTopBar(title = likedMeEntryWord(), onBack = onBack) }) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(scrollState)
                .padding(horizontal = Spacing.gutter, vertical = Spacing.lg),
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            SectionHeader(
                title = likedMeEntryWord(),
                subtitle = "Процент на строке читается из записи лайка, а не считается заново: " +
                    "это тот процент, который увидели у того, кто вас лайкнул.",
            )

            // How far the walk has come, in the reader's own words. The count is what the device
            // actually holds — never a total the server did not name, because a page knows how many
            // taps it read and nothing about how many the account made.
            if (!state.loading && state.likes.isNotEmpty()) {
                Text(
                    likedMeShownWord(state.likes.size, state.truncated),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (state.error != null && state.likes.isNotEmpty()) {
                InlineNotice(
                    text = state.error!!,
                    actionLabel = "Повторить",
                    onAction = vm::load,
                )
            }

            when {
                state.loading -> ListSkeleton()
                state.error != null -> ErrorState(
                    title = "Не удалось прочитать лайки",
                    message = state.error!!,
                    onRetry = vm::load,
                )
                state.likes.isEmpty() -> EmptyState(
                    title = "Пока никто не лайкнул",
                    message = "Здесь появятся те, кто выбрал вас сердцем. Ваш ответ с этой страницы " +
                        "создаёт пару, если человек уже лайкнул вас в ответ.",
                    actionLabel = "Обновить",
                    onAction = vm::load,
                )

                else -> state.likes.forEach { like ->
                    AppCard(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { onOpenProfile(like.userId) },
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
                                    likedRowWord(like),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                                Text(
                                    likedScoreWord(like),
                                    style = MaterialTheme.typography.labelMedium.tabularDigits(),
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                            TextButton(
                                onClick = { vm.respond(like.userId) },
                                enabled = !state.busy,
                                // The name sits in the sibling column, so the tap alone would read as
                                // «Нравится» with nobody it belongs to.
                                modifier = Modifier.semantics { contentDescription = namedVerbOnRow("Лайк в ответ", like.name) },
                            ) {
                                Text("Нравится")
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
                    words = LIKED_ME_TAIL_WORDS,
                    onRepeat = vm::retryMore,
                    onReread = vm::load,
                )
            }
        }
    }
}

private val LIKED_ME_TAIL_WORDS = PageTailWords(
    loading = "Догружаю, кто вас лайкнул…",
    moreAvailable = "Те, кто вас лайкнул, ещё не кончились. Догружается само, когда вы доходите до конца.",
    waitingForReread = "Те, кто вас лайкнул, ещё не кончились. Перечитайте список, и обход пойдёт дальше.",
    end = "Дальше тех, кто вас лайкнул, нет.",
)

/**
 * How far the walk has come: the rows on the screen, and whether the list goes on past them.
 */
internal fun likedMeShownWord(shown: Int, truncated: Boolean): String =
    shownWord(shown, truncated, "лайк", "лайка", "лайков")

/**
 * The row's second line: who this person is, and the day their tap was written.
 *
 * The day comes off the server's own moment and is dropped rather than guessed when that text cannot
 * be read as one — a list about who chose the account has no business inventing a date for it.
 */
internal fun likedRowWord(like: IncomingLike, zone: ZoneId = ZoneId.systemDefault()): String {
    val identity = "${like.age} · ${like.city}"
    val day = runCatching {
        OffsetDateTime.parse(like.likedAt)
            .atZoneSameInstant(zone)
            .format(DateTimeFormatter.ofPattern("d MMMM yyyy", Locale("ru")))
    }.getOrNull() ?: return identity
    return "$identity · $day"
}

/**
 * The row's third line: the percent the tap carried, or the sentence that says none does.
 *
 * A missing percent is not zero and not «ещё не посчитано»: the row was written before percents were
 * stored on likes, and inventing one would show the account a number its tapper never saw.
 */
internal fun likedScoreWord(like: IncomingLike): String =
    like.compatibility?.let { "Совместимость $it%" } ?: "Процент не записан"
