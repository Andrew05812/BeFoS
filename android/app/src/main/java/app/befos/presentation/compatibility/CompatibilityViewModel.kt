package app.befos.presentation.compatibility

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Compatibility
import app.befos.domain.repository.MatchRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class CompatibilityUiState(
    val loading: Boolean = true,
    val data: Compatibility? = null,
    val error: String? = null,
)

class CompatibilityViewModel(
    private val matchRepository: MatchRepository,
    private val matchId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(CompatibilityUiState())
    val uiState: StateFlow<CompatibilityUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = matchRepository.compatibility(matchId)) {
                is ApiResult.Success -> _uiState.update { it.copy(loading = false, data = result.data) }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }
}
