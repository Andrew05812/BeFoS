package app.befos.presentation.recommendations

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Recommendation
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.MatchRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class RecommendationsUiState(
    val loading: Boolean = true,
    val items: List<Recommendation> = emptyList(),
    val selected: Set<Int> = emptySet(),
    val error: String? = null,
    val selectError: String? = null,
)

class RecommendationsViewModel(
    private val matchRepository: MatchRepository,
    private val chatRepository: ChatRepository,
    private val matchId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(RecommendationsUiState())
    val uiState: StateFlow<RecommendationsUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = matchRepository.recommendations(matchId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(loading = false, items = result.data.sortedBy { r -> r.position })
                }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    fun select(activityId: Int, title: String) {
        if (_uiState.value.selected.contains(activityId)) return
        _uiState.update { it.copy(selected = it.selected + activityId, selectError = null) }
        viewModelScope.launch {
            // The proposal only exists once the pair can read it; the recorded choice
            // is a side effect for the next recommendation pass.
            // Titles are noun phrases ("Вечер настольных игр"), so the frame must not add a verb.
            when (val result = chatRepository.send(matchId, "Идея для нас: $title. Что скажете?")) {
                is ApiResult.Success -> matchRepository.selectRecommendation(matchId, activityId)
                is ApiResult.Error -> _uiState.update {
                    it.copy(selected = it.selected - activityId, selectError = result.message)
                }
            }
        }
    }
}
