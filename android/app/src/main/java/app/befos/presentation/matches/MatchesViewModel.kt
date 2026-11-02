package app.befos.presentation.matches

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.core.network.BROKEN_PAGE_LINK_CODE
import app.befos.domain.model.MatchSummary
import app.befos.presentation.common.PageWalk
import app.befos.domain.repository.MatchRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class MatchesUiState(
    val loading: Boolean = true,
    val matches: List<MatchSummary> = emptyList(),
    val error: String? = null,
    /**
     * A background refresh failed and the previous list stayed on screen. Separate from
     * [error], which blocks the screen: this one says visible content may be out of date.
     */
    val refreshError: String? = null,
    /**
     * The server stopped at its page and said more pairs stand behind it. The screen had no such line
     * while the door answered the whole list at once — every pair it knew about was on it.
     */
    val truncated: Boolean = false,
    /** The link the last answer handed out; null means the walk is over. */
    val nextCursor: String? = null,
    /** How many pages the reader has turned through, counting the first one. */
    val pages: Int = 0,
    /** The next page is on the wire; the pairs already listed stay listed. */
    val loadingMore: Boolean = false,
    /** A page behind the first one failed — kept apart from [error], which would blank the screen. */
    val moreError: String? = null,
    /** The machine code behind [moreError]: a refused link is dropped, a failed page is asked again. */
    val moreErrorCode: String = "",
    /** The pair whose row opened the «Убрать пару» dialog; null means no dialog stands open. */
    val confirmDissolve: MatchSummary? = null,
    /** A dissolve is in flight. Guards both the dialog tap and the row tap, like `blocksBusy`. */
    val dissolveBusy: Boolean = false,
    /**
     * What the last dissolve answered — the pair is gone, or why it is still here. Kept apart
     * from [error]/[refreshError], which speak about reading the list, not about this write.
     */
    val dissolveNotice: String? = null,
    val dissolveNoticeIsError: Boolean = false,
) {
    val isEmpty: Boolean get() = !loading && error == null && matches.isEmpty()

    /** More pairs exist, nothing is already asking for them, and the walk was not stopped by a refusal. */
    val canLoadMore: Boolean
        get() = nextCursor != null &&
            !loadingMore && !loading && !dissolveBusy && error == null && moreError == null

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

class MatchesViewModel(private val matchRepository: MatchRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(MatchesUiState())
    val uiState: StateFlow<MatchesUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null, refreshError = null) }
        viewModelScope.launch {
            when (val result = matchRepository.matches(null)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loading = false,
                        matches = result.data.matches,
                        truncated = result.data.truncated,
                        nextCursor = result.data.nextCursor,
                        pages = 1,
                        loadingMore = false,
                        moreError = null,
                        moreErrorCode = "",
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        loading = false,
                        error = result.message,
                        nextCursor = null,
                        loadingMore = false,
                        moreError = null,
                        moreErrorCode = "",
                    )
                }
            }
        }
    }

    /**
     * Re-fetch the newest page without flashing the skeleton; used when the tab is re-opened.
     *
     * The walk starts over here, and that is the honest reading of a refresh: the reader asked what
     * their pairs look like now, so the screen shows the top of that list rather than the page they
     * happened to be standing on.
     */
    fun refreshSilently() {
        if (_uiState.value.loading || _uiState.value.loadingMore) return
        viewModelScope.launch {
            when (val result = matchRepository.matches(null)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loading = false,
                        matches = result.data.matches,
                        truncated = result.data.truncated,
                        nextCursor = result.data.nextCursor,
                        pages = 1,
                        moreError = null,
                        moreErrorCode = "",
                        error = null,
                        refreshError = null,
                    )
                }
                // Keeping the old list is right; saying nothing about it is not: an unread
                // pair that did not arrive looks like a pair that does not exist. An empty
                // list has no cached content to stand on, so there the failure is the screen.
                // The frontier goes with the page this read was replacing — a link into a list the
                // screen just failed to re-read is a key into nothing.
                is ApiResult.Error -> _uiState.update { state ->
                    if (state.matches.isEmpty()) state.copy(loading = false, error = result.message, nextCursor = null)
                    else state.copy(refreshError = result.message, nextCursor = null, moreError = null)
                }
            }
        }
    }

    /** Turn the page: the pairs already listed stay listed while the older ones are on the wire. */
    fun loadMore() {
        val state = _uiState.value
        val cursor = state.nextCursor ?: return
        if (state.loadingMore || state.loading || state.dissolveBusy || state.error != null) return
        _uiState.update { it.copy(loadingMore = true, moreError = null, moreErrorCode = "") }
        viewModelScope.launch {
            when (val result = matchRepository.matches(cursor)) {
                is ApiResult.Success -> _uiState.update { current ->
                    val held = current.matches.map { it.matchId }.toSet()
                    current.copy(
                        matches = current.matches + result.data.matches.filter { it.matchId !in held },
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
     * with the same key; a key the server refuses is dropped and the list re-read from its newest page,
     * because a frontier the door will not open has nothing behind it to ask for.
     */
    fun retryMore() {
        if (_uiState.value.moreErrorCode == BROKEN_PAGE_LINK_CODE) load() else loadMore()
    }

    /**
     * Arms the dialog for one pair. A write is already in flight, so the tap is dropped rather
     * than arming a dialog whose confirm would only return on its own guard.
     */
    fun askDissolve(match: MatchSummary) {
        if (_uiState.value.dissolveBusy) return
        _uiState.update { it.copy(confirmDissolve = match) }
    }

    fun cancelDissolve() {
        _uiState.update { it.copy(confirmDissolve = null) }
    }

    /**
     * Ends the pair and drops the row from the list the server's answer confirms it.
     *
     * 204 carries no list, so the row leaves by `matchId` after the answer arrives — never before:
     * a row removed on tap would paint the pair gone while the server still holds it, and a refusal
     * would leave the screen claiming a pair the list still answers. The row stays on a failed
     * write with the server's words named beside it.
     */
    fun confirmDissolve() {
        val match = _uiState.value.confirmDissolve ?: return
        if (_uiState.value.dissolveBusy) return
        _uiState.update { it.copy(confirmDissolve = null, dissolveBusy = true) }
        viewModelScope.launch {
            when (val result = matchRepository.dissolve(match.matchId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        dissolveBusy = false,
                        matches = it.matches.filterNot { row -> row.matchId == match.matchId },
                        dissolveNoticeIsError = false,
                        // The name stays out of the notice: the list itself says who is gone, and
                        // «Пара с Аня убрана» would be the nominative case where grammar wants the
                        // instrument — the dialog above is where the name was addressed.
                        dissolveNotice = "Пара убрана. Переписка и планы не вернутся.",
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(dissolveBusy = false, dissolveNoticeIsError = true, dissolveNotice = result.message)
                }
            }
        }
    }

    fun clearDissolveNotice() {
        _uiState.update { it.copy(dissolveNotice = null) }
    }
}
