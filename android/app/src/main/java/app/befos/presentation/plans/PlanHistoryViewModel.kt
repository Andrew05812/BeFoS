package app.befos.presentation.plans

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Message
import app.befos.domain.repository.PlanRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PlanHistoryUiState(
    val loading: Boolean = true,
    val events: List<Message> = emptyList(),
    val error: String? = null,
)

/**
 * The story of one plan, read from the record the server keeps rather than from this visit.
 *
 * One request asks for the plan and gets its chronology with it, which is why this page holds no list
 * of its own and no socket: the arrangement's moves are already announced to the pair's plans page,
 * and a second listener on the same thread would ask the person to read one change twice. What the
 * page cannot inherit is the list the tap came from — a plan the pair moved while this screen was
 * closed is here as the server now tells it, and a refused read says so instead of showing the empty
 * chronology of a plan nobody has touched.
 */
class PlanHistoryViewModel(
    private val planRepository: PlanRepository,
    private val planId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PlanHistoryUiState())
    val uiState: StateFlow<PlanHistoryUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = planRepository.history(planId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(loading = false, events = result.data, error = null)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loading = false, error = result.message)
                }
            }
        }
    }
}
