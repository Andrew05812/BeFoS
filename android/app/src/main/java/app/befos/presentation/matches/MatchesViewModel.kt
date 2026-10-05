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
}
