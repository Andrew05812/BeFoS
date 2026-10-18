package app.befos.presentation.moderation

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.ReportCard
import app.befos.domain.model.ReportDetail
import app.befos.domain.repository.ModerationRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * How much a moderator may write about a decision. The number is the server's own
 * (`MAX_COMMENT` in `moderation_service.py`), and clamping it here is what keeps a long account of a
 * bad evening from coming back as a validation error the reader cannot fix.
 */
const val MaxReviewComment: Int = 1000

data class ModerationUiState(
    /**
     * The status the queue is filtered by, or null for every status. A filter is a request parameter
     * rather than a list the screen trims itself: the queue is paged, and trimming a page locally
     * would hide rows the server still holds behind the cursor.
     */
    val filter: String? = null,
    val reports: List<ReportCard> = emptyList(),
    val loading: Boolean = true,
    val loadingMore: Boolean = false,
    val nextCursor: String? = null,
    val hasMore: Boolean = false,
    /** The read failed and nothing stands on screen to be drawn instead. */
    val error: String? = null,
    /** A re-read failed while the rows already drawn stay: the list may be out of date. */
    val refreshError: String? = null,
    val detail: ReportDetail? = null,
    val detailLoading: Boolean = false,
    val detailError: String? = null,
    val chosenStatus: String = "",
    val comment: String = "",
    val deciding: Boolean = false,
    val decisionError: String? = null,
)

class ModerationViewModel(private val moderation: ModerationRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(ModerationUiState())
    val uiState: StateFlow<ModerationUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    /** First page of the current filter, drawn from the skeleton. */
    fun load() {
        _uiState.update { it.copy(loading = true, error = null, refreshError = null) }
        viewModelScope.launch {
            when (val result = moderation.page(_uiState.value.filter, null)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loading = false,
                        reports = result.data.reports,
                        nextCursor = result.data.nextCursor,
                        hasMore = result.data.hasMore,
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        loading = false,
                        reports = emptyList(),
                        nextCursor = null,
                        hasMore = false,
                        error = result.message,
                    )
                }
            }
        }
    }

    /**
     * The filter chips call this. The complaint left open is closed with it: a panel about a row the
     * new filter excludes would read as part of the set the chip names, and the operator would be
     * deciding a complaint that is not in the list above it.
     */
    fun setFilter(status: String?) {
        if (_uiState.value.filter == status) return
        _uiState.update {
            it.copy(
                filter = status,
                detail = null,
                detailError = null,
                chosenStatus = "",
                comment = "",
                decisionError = null,
            )
        }
        load()
    }

    /** Follows the cursor the last page returned and appends what the server answers with. */
    fun loadMore() {
        val current = _uiState.value
        if (current.loadingMore || !current.hasMore) return
        val cursor = current.nextCursor ?: return
        _uiState.update { it.copy(loadingMore = true, refreshError = null) }
        viewModelScope.launch {
            when (val result = moderation.page(current.filter, cursor)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loadingMore = false,
                        reports = it.reports + result.data.reports,
                        nextCursor = result.data.nextCursor,
                        hasMore = result.data.hasMore,
                    )
                }
                // The rows already drawn stay: a queue that will not grow is still a queue read
                // halfway, and the line under it says which half.
                is ApiResult.Error -> _uiState.update {
                    it.copy(loadingMore = false, refreshError = result.message)
                }
            }
        }
    }

    /**
     * Reads one complaint: its history and the statuses the server still lets it move to.
     *
     * The choices are read rather than derived. The client names the four statuses for the filter
     * chips, and computing «neither resolved nor dismissed» locally would be one line shorter — which
     * is exactly how a second copy of the transition table starts, and the second copy is the one
     * that drifts when the server's table grows.
     */
    fun openDetail(reportId: String) {
        _uiState.update {
            it.copy(
                detail = null,
                detailLoading = true,
                detailError = null,
                chosenStatus = "",
                comment = "",
                decisionError = null,
            )
        }
        viewModelScope.launch {
            when (val result = moderation.detail(reportId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(detail = result.data, detailLoading = false)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(detailLoading = false, detailError = result.message)
                }
            }
        }
    }

    fun closeDetail() = _uiState.update {
        it.copy(
            detail = null,
            detailLoading = false,
            detailError = null,
            chosenStatus = "",
            comment = "",
            decisionError = null,
        )
    }

    fun chooseStatus(status: String) = _uiState.update {
        it.copy(chosenStatus = status, decisionError = null)
    }

    fun setComment(value: String) = _uiState.update {
        it.copy(comment = value.take(MaxReviewComment), decisionError = null)
    }

    /**
     * Writes the decision, then re-reads both halves it changes.
     *
     * The write answers with the status the row holds after its own commit, which is not always the
     * status that was asked for — a second moderator can have moved the complaint first, and then the
     * refusal naming the current status is the honest answer. Neither half is patched from that
     * answer alone: the page is re-read because a filtered queue may now exclude the row, and the
     * panel is re-read because a complaint that moved has different statuses left to it and one more
     * line of history, which is the record the next moderator reads.
     */
    fun decide() {
        val current = _uiState.value
        val detail = current.detail ?: return
        if (current.deciding) return
        val status = current.chosenStatus
        if (status !in detail.allowedNextStatuses) {
            _uiState.update { it.copy(decisionError = "Этот статус жалобе уже недоступен. Обновите жалобу.") }
            return
        }
        _uiState.update { it.copy(deciding = true, decisionError = null) }
        viewModelScope.launch {
            val note = current.comment.trim()
            val result = moderation.review(detail.card.id, status, note.ifBlank { null })
            if (result is ApiResult.Error) {
                _uiState.update { it.copy(deciding = false, decisionError = result.message) }
                return@launch
            }
            _uiState.update {
                it.copy(deciding = false, chosenStatus = "", comment = "", detail = null, detailLoading = true)
            }
            when (val fresh = moderation.detail(detail.card.id)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(detail = fresh.data, detailLoading = false)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(detailLoading = false, detailError = fresh.message)
                }
            }
            when (val page = moderation.page(_uiState.value.filter, null)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        reports = page.data.reports,
                        nextCursor = page.data.nextCursor,
                        hasMore = page.data.hasMore,
                    )
                }
                is ApiResult.Error -> _uiState.update { state ->
                    if (state.reports.isEmpty()) state.copy(error = page.message) else state.copy(refreshError = page.message)
                }
            }
        }
    }
}
