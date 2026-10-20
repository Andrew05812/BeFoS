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
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.PassedUser
import app.befos.presentation.common.passedEntryWord
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

    Scaffold(topBar = { AppTopBar(title = passedEntryWord(), onBack = onBack) }) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
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
            // A page that stopped at fifty says so. Without this line the list would claim it named
            // everybody the account ever passed, which is the one sentence it cannot know.
            if (state.truncated && !state.loading) {
                InlineNotice(
                    text = "Показаны пятьдесят самых свежих пропусков, за ними ждут другие. " +
                        "Эта страница не следит за списком сама — обновите её.",
                    isError = false,
                    actionLabel = "Обновить",
                    onAction = vm::load,
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
        }
    }
}

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
