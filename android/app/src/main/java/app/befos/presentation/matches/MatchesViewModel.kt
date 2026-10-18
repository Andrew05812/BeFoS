package app.befos.presentation.matches

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.MatchSummary
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
)

class MatchesViewModel(private val matchRepository: MatchRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(MatchesUiState())
    val uiState: StateFlow<MatchesUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null, refreshError = null) }
        viewModelScope.launch {
            when (val result = matchRepository.matches()) {
                is ApiResult.Success -> _uiState.update { it.copy(loading = false, matches = result.data) }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    /** Re-fetch without flashing the skeleton; used when the tab is re-opened. */
    fun refreshSilently() {
        if (_uiState.value.loading) return
        viewModelScope.launch {
            when (val result = matchRepository.matches()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(loading = false, matches = result.data, error = null, refreshError = null)
                }
                // Keeping the old list is right; saying nothing about it is not: an unread
                // pair that did not arrive looks like a pair that does not exist. An empty
                // list has no cached content to stand on, so there the failure is the screen.
                is ApiResult.Error -> _uiState.update { state ->
                    if (state.matches.isEmpty()) state.copy(loading = false, error = result.message)
                    else state.copy(refreshError = result.message)
                }
            }
        }
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
