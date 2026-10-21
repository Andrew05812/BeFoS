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
import app.befos.core.designsystem.SectionHeader
import app.befos.core.designsystem.Spacing
import app.befos.core.designsystem.tabularDigits
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.OutgoingLike
import app.befos.presentation.common.myLikesEntryWord
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * Whom this account tapped, read from the rows those taps wrote, with the one verb that takes a tap
 * back.
 *
 * The account could already read both other halves of its social life — who came to it, and who it
 * dismissed — while its own hearts stayed a write with no read. This page draws the vocabulary the
 * inbox and the pass list already use and puts its action on the row itself: a visible word, not a
 * gesture hidden behind a control.
 */
@Composable
fun MyLikesScreen(onBack: () -> Unit, onOpenProfile: (String) -> Unit) {
    val vm: MyLikesViewModel = beFosViewModel { MyLikesViewModel(it.discoveryRepository) }
    val state by vm.uiState.collectAsState()

    Scaffold(topBar = { AppTopBar(title = myLikesEntryWord(), onBack = onBack) }) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = Spacing.gutter, vertical = Spacing.lg),
            verticalArrangement = Arrangement.spacedBy(Spacing.lg),
        ) {
            SectionHeader(
                title = myLikesEntryWord(),
                subtitle = "Процент на строке читается из записи лайка, а не считается заново: " +
                    "это тот процент, который стоял на карточке в минуту вашего касания.",
            )

            // The row is gone from this page the moment the write lands, so the notice has to say whose
            // tap it withdrew and what the withdrawal deliberately did not do — end a pair.
            state.withdrawn?.let { name ->
                InlineNotice(
                    text = "$name больше не лайкнут. Если к этому моменту пара уже сложилась, она " +
                        "остаётся — убрать её можно на экране пар.",
                    isError = false,
                    actionLabel = "Скрыть",
                    onAction = vm::dismissWithdrawn,
                )
            }
            // A page that stopped at fifty says so. Without this line the list would claim it named
            // everybody the account ever liked, which is the one sentence it cannot know.
            if (state.truncated && !state.loading) {
                InlineNotice(
                    text = "Показаны пятьдесят самых свежих касаний, за ними ждут другие. " +
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
                    title = "Не удалось прочитать ваши лайки",
                    message = state.error!!,
                    onRetry = vm::load,
                )
                state.likes.isEmpty() -> EmptyState(
                    title = "Вы пока никого не лайкали",
                    message = "Здесь появятся те, кого вы выбрали сердцем. Отзыв лайка не распускает " +
                        "готовую пару и не трогает чужой ответ — только ваше касание.",
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
                                onClick = { vm.withdraw(like.userId) },
                                enabled = !state.busy,
                                // The name sits in the sibling column, so the tap alone would read as
                                // «Забрать лайк» with nobody it belongs to.
                                modifier = Modifier.semantics { contentDescription = "Забрать лайк для ${like.name}" },
                            ) {
                                Text("Забрать лайк")
                            }
                        }
                    }
                }
            }
        }
    }
}

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
