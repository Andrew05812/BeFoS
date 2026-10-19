package app.befos.presentation.discovery

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import app.befos.presentation.common.likedMeEntryWord
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
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Spacing.gutter, vertical = Spacing.lg),
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            SectionHeader(
                title = likedMeEntryWord(),
                subtitle = "Процент на строке читается из записи лайка, а не считается заново: " +
                    "это тот процент, который увидели у того, кто вас лайкнул.",
            )

            // A page that stopped at fifty says so. Without this line the list would claim it showed
            // everyone who ever tapped, which is the one sentence it cannot know.
            if (state.truncated && !state.loading) {
                InlineNotice(
                    text = "Показаны пятьдесят самых свежих лайков, за ними ждут другие. " +
                        "Эта страница не следит за списком сама — обновите её.",
                    isError = false,
                    actionLabel = "Обновить",
                    onAction = vm::load,
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
                                modifier = Modifier.semantics { contentDescription = "Лайк в ответ для ${like.name}" },
                            ) {
                                Text("Нравится")
                            }
                        }
                    }
                }
            }
        }
    }
}

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
