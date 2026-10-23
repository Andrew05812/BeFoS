package app.befos.presentation.discovery

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.OutgoingLike
import app.befos.domain.repository.DiscoveryRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class MyLikesUiState(
    val loading: Boolean = true,
    val likes: List<OutgoingLike> = emptyList(),
    /**
     * The server stopped at its page and said more taps stand behind what this screen holds. Without
     * this line the list would claim it named every person the account ever liked, which is the one
     * thing it cannot know.
     */
    val truncated: Boolean = false,
    /**
     * The link the last answer handed out, and the only thing that reaches the taps behind it. Null
     * means the walk is over: the server said nothing stands beyond the rows this screen holds.
     */
    val nextCursor: String? = null,
    /** How many pages the reader has turned through, counting the first one. */
    val pages: Int = 0,
    /** The next page is on the wire; the rows already shown stay on screen while it waits. */
    val loadingMore: Boolean = false,
    /**
     * A page behind the first one failed. It is kept apart from [error] on purpose: the rows above are
     * real and still drawn, and a full-screen failure would say the account's history could not be read
     * when only its older half did not come.
     */
    val moreError: String? = null,
    val busy: Boolean = false,
    /** The row whose withdrawal is on the wire, so that one card can say so while the others stand. */
    val withdrawing: String? = null,
    val error: String? = null,
    val withdrawn: String? = null,
) {
    val isEmpty: Boolean get() = !loading && error == null && likes.isEmpty()

    /** More taps exist and nothing is already on the wire asking for them. */
    val canLoadMore: Boolean get() = nextCursor != null && !loadingMore && !loading && error == null
}

// The row staying put is the honest part of a failed withdrawal: a transport line alone would describe
// a socket, while this says the tap is still written and the person is still in this list.
private const val WITHDRAW_NOT_RECORDED = "Лайк не отозван — человек остался в списке."

/**
 * The account's own read of the taps it left standing, the verb that takes a tap back, and the walk
 * from one page of that history to the next.
 *
 * One request paints the first page and hands over the key to the rest of it. Stage 116 shipped this
 * screen knowing the list was longer than the page — the server said `has_more` and the client wrote
 * «за ними ждут другие» — and unable to do anything about it, because the door took no cursor. The page
 * count in [MyLikesUiState.pages] is what that gap looked like from the device: fifty rows, and the
 * account's own history stopping there. The stand names the size of it: 87 / 893 / 4 493 outgoing taps
 * at the three scales its table publishes.
 *
 * A withdrawal replaces the page with the server's answer rather than removing the tapped row locally,
 * because the write and the read are the same question: a person the server still holds has to stay
 * visible with a working tap. Once the reader has turned past the first page the answer describes a
 * page they have already walked through, so the row this write removed leaves the list and the reader's
 * own frontier stays where they put it — the server's link is keyed to a moment, not to a row count, so
 * a row that went from behind does not move the pages in front of it.
 *
 * Nothing is published to the deck's answered-users stream here, and that is the difference between
 * this verb and the inbox's own reply. Answering a tap means the account has spoken about that person,
 * so the deck must not ask again. Taking a tap back means the opposite — the account has unspoken — and
 * the person becomes eligible again, which the deck discovers on its own next refill because the
 * anti-join that excluded them no longer finds a row.
 */
class MyLikesViewModel(
    private val discoveryRepository: DiscoveryRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(MyLikesUiState())
    val uiState: StateFlow<MyLikesUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.liked(null)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loading = false,
                        likes = result.data.likes,
                        truncated = result.data.truncated,
                        nextCursor = result.data.nextCursor,
                        pages = 1,
                        loadingMore = false,
                        moreError = null,
                        error = null,
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loading = false, loadingMore = false, error = result.message)
                }
            }
        }
    }

    /**
     * Turn the page. The rows already on screen stay there while the next page is on the wire, and a
     * page that does not come leaves them: the account's history is not unmade by one failed read of its
     * older half, and the notice with «Повторить» is what says which part is missing.
     *
     * A person who taps the same row twice, or scrolls to the end twice before the first answer lands,
     * gets one request — [MyLikesUiState.canLoadMore] is false while a page is out, and the guard is
     * read once before the coroutine starts rather than after it resumes.
     */
    fun loadMore() {
        val cursor = _uiState.value.nextCursor ?: return
        if (!_uiState.value.canLoadMore) return
        _uiState.update { it.copy(loadingMore = true, moreError = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.liked(cursor)) {
                is ApiResult.Success -> _uiState.update { current ->
                    val page = result.data
                    val held = current.likes.map { it.userId }.toSet()
                    // A row the server names twice enters the list once. The keyset cannot repeat a
                    // gesture on its own, but a person who liked somebody again between two pages wrote
                    // a fresh row, and a list that showed the same face twice would be this screen's
                    // bug rather than the server's.
                    current.copy(
                        likes = current.likes + page.likes.filter { it.userId !in held },
                        truncated = page.truncated,
                        nextCursor = page.nextCursor,
                        pages = current.pages + 1,
                        loadingMore = false,
                        moreError = null,
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loadingMore = false, moreError = result.message)
                }
            }
        }
    }

    /**
     * Take one tap back. The person leaves this list because the server said so, and the notice names
     * them: the row is gone from the screen the moment the write lands, and a message that pointed at
     * nobody would leave the reader wondering whether the tap did anything at all.
     *
     * A refusal — a tap already taken back, a person who has gone, a pair the account did not form —
     * leaves the list exactly as it stood and says what the server said, rather than hiding a row that
     * is still written.
     */
    fun withdraw(userId: String) {
        if (_uiState.value.busy) return
        val name = _uiState.value.likes.firstOrNull { it.userId == userId }?.name
        _uiState.update { it.copy(busy = true, withdrawing = userId, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.unlike(userId)) {
                is ApiResult.Success -> _uiState.update { current ->
                    if (current.pages <= 1) {
                        // The screen is holding the page the write answered, so the answer is the list.
                        current.copy(
                            busy = false,
                            withdrawing = null,
                            likes = result.data.likes,
                            truncated = result.data.truncated,
                            nextCursor = result.data.nextCursor,
                            error = null,
                            withdrawn = name,
                        )
                    } else {
                        // Deeper than the first page, the answer describes rows this reader has walked
                        // past. Adopting it would drop the older half of the list the server still holds
                        // and move the frontier back to the top; the row this write removed leaves, and
                        // the rest of the walk stays where the reader left it.
                        current.copy(
                            busy = false,
                            withdrawing = null,
                            likes = current.likes.filter { it.userId != userId },
                            error = null,
                            withdrawn = name,
                        )
                    }
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        busy = false,
                        withdrawing = null,
                        error = "$WITHDRAW_NOT_RECORDED ${result.message}",
                    )
                }
            }
        }
    }

    /** The notice has been read; the row it named is already gone from the list. */
    fun dismissWithdrawn() {
        _uiState.update { it.copy(withdrawn = null) }
    }
}
