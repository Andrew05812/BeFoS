package app.befos.presentation.discovery

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.core.network.BROKEN_PAGE_LINK_CODE
import app.befos.domain.model.PassedUser
import app.befos.presentation.common.PageWalk
import app.befos.domain.repository.DiscoveryRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PassedUiState(
    val loading: Boolean = true,
    val passed: List<PassedUser> = emptyList(),
    /**
     * The server stopped at its page and said more answers stand behind it. Without this line the list
     * would claim it named every person the account ever passed, which is the one thing it cannot know.
     */
    val truncated: Boolean = false,
    /** The link the last answer handed out; null means the walk is over. */
    val nextCursor: String? = null,
    /** How many pages the reader has turned through, counting the first one. */
    val pages: Int = 0,
    /** The next page is on the wire; what is already shown stays on screen while it waits. */
    val loadingMore: Boolean = false,
    /** A page behind the first one failed, kept apart from [error] so the rows above stay drawn. */
    val moreError: String? = null,
    /** The machine code behind [moreError]: a refused link is dropped, a failed page is asked again. */
    val moreErrorCode: String = "",
    val busy: Boolean = false,
    val error: String? = null,
    /**
     * Whose answer is being taken back, so the row can be named in the notice the write leaves
     * behind. The name comes from the row the server listed, never from a cached profile.
     */
    val released: String? = null,
) {
    val isEmpty: Boolean get() = !loading && error == null && passed.isEmpty()

    /** More passes exist, nothing is already asking for them, and the walk was not stopped by a refusal. */
    val canLoadMore: Boolean
        get() = nextCursor != null &&
            !loadingMore && !loading && !busy && error == null && moreError == null

    /** The same facts every paged list hands the shared tail resolver. */
    fun walk(): PageWalk = PageWalk(
        loadingMore = loadingMore,
        moreError = moreError,
        moreErrorCode = moreErrorCode,
        truncated = truncated,
        nextCursor = nextCursor,
        pages = pages,
    )
}

// The row staying put is the honest part of a failed release: a transport line alone would describe
// a socket, while this says the answer is still written and the person is still out of the deck.
private const val RELEASE_NOT_RECORDED = "Возврат не записан — человек остался в списке."

/**
 * The account's own read of the cards it passed, the one verb that takes an answer back, and the walk
 * from one page of that list to the next.
 *
 * One request paints the first page and hands over the key to the rest. Stage 114 opened this door and
 * stage 115 priced it, and until stage 126 its `has_more` had no verb beside it — the stand holds 315 /
 * 3 109 / 15 509 passes for one reader at its three scales, so the unread tail was not a corner case.
 *
 * A release replaces the page with the server's answer rather than subtracting the tapped row locally,
 * because the write and the read are the same question: a person the server still holds has to stay
 * visible with a working tap. Once the reader has walked past the first page, though, the answer
 * describes rows they have already left behind, so the released row leaves and the frontier stays.
 * The deck is deliberately not told about a release — the returned person cannot rejoin the page
 * already in memory, since ranks are assigned once and a release re-queues through the normal refill,
 * so the deck meets them on its own next load and the screen says so instead of promising them at the
 * front.
 */
class PassedViewModel(
    private val discoveryRepository: DiscoveryRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PassedUiState())
    val uiState: StateFlow<PassedUiState> = _uiState.asStateFlow()

    /**
     * Есть ли на проводе чтение. Полю `loading` для этого доверия нет: начальное состояние стоит на
     * `loading = true` ещё до первого обращения, и проверка по нему отменила бы то самое чтение,
     * которое делает `init`.
     */
    private var readOnTheWire = false

    init {
        load()
    }

    fun load() {
        if (readOnTheWire) return
        readOnTheWire = true
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            val result = discoveryRepository.passed(null)
            // Снимается до, а не внутри `update`: блок обновления StateFlow перепускается, если с
            // состоянием в этот момент работал кто-то ещё.
            readOnTheWire = false
            when (result) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loading = false,
                        passed = result.data.passed,
                        truncated = result.data.truncated,
                        nextCursor = result.data.nextCursor,
                        pages = 1,
                        loadingMore = false,
                        moreError = null,
                        moreErrorCode = "",
                        error = null,
                    )
                }
                // The rows stay — one failed refresh does not unmake the answers the account gave —
                // but the frontier goes with the page this read was replacing.
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        loading = false,
                        loadingMore = false,
                        error = result.message,
                        nextCursor = null,
                        moreError = null,
                        moreErrorCode = "",
                    )
                }
            }
        }
    }

    /** Turn the page: what is on the screen stays there while the older half is on the wire. */
    fun loadMore() {
        val state = _uiState.value
        val cursor = state.nextCursor ?: return
        if (state.busy || state.loadingMore || state.loading || state.error != null) return
        _uiState.update { it.copy(loadingMore = true, moreError = null, moreErrorCode = "") }
        viewModelScope.launch {
            when (val result = discoveryRepository.passed(cursor)) {
                is ApiResult.Success -> _uiState.update { current ->
                    val held = current.passed.map { it.userId }.toSet()
                    current.copy(
                        passed = current.passed + result.data.passed.filter { it.userId !in held },
                        truncated = result.data.truncated,
                        nextCursor = result.data.nextCursor,
                        pages = current.pages + 1,
                        loadingMore = false,
                        moreError = null,
                        moreErrorCode = "",
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loadingMore = false, moreError = result.message, moreErrorCode = result.errorCode)
                }
            }
        }
    }

    /**
     * The verb on the notice under a failed page. A page that only failed to arrive is asked for again
     * by the same key; a key the server refuses is dropped and the list is read from the newest page,
     * because the frontier it names is not coming back.
     */
    fun retryMore() {
        if (_uiState.value.moreErrorCode == BROKEN_PAGE_LINK_CODE) load() else loadMore()
    }

    /**
     * Take one pass back. The person leaves this list because the server said so, and the notice
     * names them: the row is gone from the screen the moment the write lands, and a message that
     * pointed at nobody would leave the reader wondering whether the tap did anything at all.
     *
     * A refusal — an answer already taken back, an account that has gone — leaves the list exactly as
     * it stood and says what the server said, rather than hiding a row that is still written.
     */
    fun release(userId: String) {
        if (_uiState.value.busy || _uiState.value.loading || _uiState.value.loadingMore) return
        val name = _uiState.value.passed.firstOrNull { it.userId == userId }?.name
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.unpass(userId)) {
                is ApiResult.Success -> _uiState.update { current ->
                    if (current.pages <= 1) {
                        // Standing on the page the write answered, so the answer is the list — and with
                        // it the walk's own frontier and any notice about a page that did not come.
                        current.copy(
                            busy = false,
                            passed = result.data.passed,
                            truncated = result.data.truncated,
                            nextCursor = result.data.nextCursor,
                            moreError = null,
                            moreErrorCode = "",
                            error = null,
                            released = name,
                        )
                    } else {
                        // Deeper than the first page the answer describes rows this reader has walked
                        // past; adopting it would drop the older half and move the frontier back to the
                        // top. The row this write released leaves, and the rest of the walk stays put.
                        current.copy(
                            busy = false,
                            passed = current.passed.filter { it.userId != userId },
                            error = null,
                            released = name,
                        )
                    }
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(busy = false, error = "$RELEASE_NOT_RECORDED ${result.message}")
                }
            }
        }
    }

    /** The notice has been read; the row it named is already gone from the list. */
    fun dismissReleased() {
        _uiState.update { it.copy(released = null) }
    }
}
