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
)

class MatchesViewModel(private val matchRepository: MatchRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(MatchesUiState())
    val uiState: StateFlow<MatchesUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = matchRepository.matches()) {
                is ApiResult.Success -> _uiState.update { it.copy(loading = false, matches = result.data) }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }
}
