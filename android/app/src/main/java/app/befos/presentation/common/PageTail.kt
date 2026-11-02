package app.befos.presentation.common

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.Spacing
import app.befos.core.network.BROKEN_PAGE_LINK
import app.befos.core.network.BROKEN_PAGE_LINK_CODE

/**
 * The one shape every paged list has below its rows: what the walk holds, and what it can still ask for.
 *
 * Four doors page now — the deck's own list of taps, the inbox, the pass list and the pairs — and the
 * tail of each of them is the same claim about the same five facts, so the claim is decided in one place
 * and drawn in one place. Stage 123 wrote this logic for the tap list alone; three more copies of the
 * same `when` is how one list's tail starts saying something the others do not.
 */
enum class PageTail {
    /** The next page is on the wire. */
    Loading,

    /** A page behind the first did not arrive, and the key to it is still good — so it can be asked again. */
    PageRefused,

    /**
     * The key itself was refused. Repeating it is not a repair: the frontier it names is gone, so the
     * only ask left is the newest page. This branch exists because the server says the two apart — a
     * link it will not open answers `broken_page_link`, and a screen that offered «Повторить» over it
     * would be inviting the reader to knock on a door that has just answered.
     */
    LinkRefused,

    /** More rows exist, the key is on the screen, and nothing is on the wire. */
    MoreAvailable,

    /**
     * The last answer that came said more rows stand behind these, and then a reload threw the key
     * away. The rows on the screen are the earlier read; the walk cannot go on from them until a fresh
     * page hands a key again — so the verb here is the reload, not a page.
     */
    WaitingForReread,

    /** The server named no rows beyond these, and the reader had turned at least one page to hear that. */
    End,

    /** One page, nothing behind it: the list itself says all there is to say. */
    Nothing,
}

/** The five facts a tail is drawn from, in the shape the shared resolver reads. */
data class PageWalk(
    val loadingMore: Boolean,
    val moreError: String?,
    val moreErrorCode: String,
    val truncated: Boolean,
    val nextCursor: String?,
    val pages: Int,
)

/**
 * Which sentence the tail draws. Two rules hold it together.
 *
 * A verb appears only where the key it needs is on the screen: «Повторить» over a page that did not
 * come and «Показать ещё» over a list that goes on both ask with [PageWalk.nextCursor], so neither
 * appears once it is null. And the words that end the walk belong to the server, not to an absent key:
 * [End] is drawn when the last answer said nothing stands beyond these rows, and never merely because
 * this screen has no link in hand.
 */
fun pageTail(walk: PageWalk): PageTail = when {
    walk.loadingMore -> PageTail.Loading
    walk.moreError != null && walk.moreErrorCode == BROKEN_PAGE_LINK_CODE -> PageTail.LinkRefused
    walk.moreError != null && walk.nextCursor != null -> PageTail.PageRefused
    walk.truncated && walk.nextCursor != null -> PageTail.MoreAvailable
    walk.truncated -> PageTail.WaitingForReread
    walk.pages > 1 -> PageTail.End
    else -> PageTail.Nothing
}

/** What one door's tail says, in that door's own words. */
data class PageTailWords(
    val loading: String,
    val moreAvailable: String,
    val waitingForReread: String,
    val end: String,
)

/**
 * The tail row itself, in the same dressings the rest of the app uses: a spinner and a line while a
 * page waits, a notice with one verb when it does not come, and a quiet sentence when the walk is over.
 *
 * [onRepeat] re-asks the key the screen holds; [onReread] drops it and reads the newest page. Every
 * branch that shows a verb is wired to the one that can actually work, which is the part a reader
 * cannot check for themselves.
 */
@Composable
fun PageTailRow(
    tail: PageTail,
    moreError: String?,
    words: PageTailWords,
    onRepeat: () -> Unit,
    onReread: () -> Unit,
) {
    when (tail) {
        PageTail.Loading -> Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = Spacing.sm),
            horizontalArrangement = Arrangement.spacedBy(Spacing.md, Alignment.CenterHorizontally),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            CircularProgressIndicator(modifier = Modifier.size(22.dp), strokeWidth = 2.5.dp)
            Text(words.loading, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }

        PageTail.PageRefused -> InlineNotice(
            text = "Следующая страница не дошла. $moreError",
            actionLabel = "Повторить",
            onAction = onRepeat,
        )

        PageTail.LinkRefused -> InlineNotice(
            // The server's own words, reused rather than restated: one event, one sentence in the app.
            text = BROKEN_PAGE_LINK,
            actionLabel = "Перечитать с самого свежего",
            onAction = onReread,
        )

        PageTail.MoreAvailable -> InlineNotice(
            text = words.moreAvailable,
            isError = false,
            actionLabel = "Показать ещё",
            onAction = onRepeat,
        )

        PageTail.WaitingForReread -> InlineNotice(
            text = words.waitingForReread,
            isError = false,
            actionLabel = "Повторить",
            onAction = onReread,
        )

        PageTail.End -> Text(
            words.end,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        PageTail.Nothing -> Unit
    }
}

/**
 * The count line above a paged list, in the grammatical case the number itself asks for.
 *
 * A screen reader says this sentence before the walk starts, and «показано 1 лайков» is not a rounding
 * difference but a number the account cannot believe — the device pass of stage 126 met it over an
 * inbox holding exactly one tap. The three forms come from the caller, because only the screen knows
 * which noun it counts, and a rule that guesses a noun's gender from a stem is how the next list gets
 * it wrong again.
 */
internal fun shownWord(shown: Int, truncated: Boolean, one: String, few: String, many: String): String {
    val word = when {
        shown % 100 in 11..14 -> many
        shown % 10 == 1 -> one
        shown % 10 in 2..4 -> few
        else -> many
    }
    return if (truncated) "Показано $shown $word, и список идёт дальше" else "Показано $shown $word — весь список"
}
