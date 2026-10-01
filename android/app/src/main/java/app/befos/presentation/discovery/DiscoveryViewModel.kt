package app.befos.presentation.discovery

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.DiscoveryCard
import app.befos.domain.model.LikeOutcome
import app.befos.domain.repository.DiscoveryRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class DiscoveryUiState(
    val loading: Boolean = true,
    val cards: List<DiscoveryCard> = emptyList(),
    val index: Int = 0,
    val refreshing: Boolean = false,
    val busy: Boolean = false,
    val error: String? = null,
    val match: LikeOutcome? = null,
) {
    val current: DiscoveryCard? get() = cards.getOrNull(index)
    val isEmpty: Boolean get() = !loading && cards.isEmpty()
}

class DiscoveryViewModel(private val discoveryRepository: DiscoveryRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(DiscoveryUiState())
    val uiState: StateFlow<DiscoveryUiState> = _uiState.asStateFlow()

    private val pageLimit = 20

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.feed(limit = pageLimit, offset = 0)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(loading = false, cards = result.data, index = 0)
                }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    fun like() {
        val card = _uiState.value.current ?: return
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.like(card.userId)) {
                is ApiResult.Success -> {
                    val outcome = result.data
                    _uiState.update { it.copy(busy = false) }
                    if (outcome.matched) {
                        _uiState.update { it.copy(match = outcome) }
                    } else {
                        advance()
                    }
                }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, error = result.message) }
            }
        }
    }

    fun pass() {
        val card = _uiState.value.current ?: return
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.pass(card.userId)) {
                is ApiResult.Success -> {
                    _uiState.update { it.copy(busy = false) }
                    advance()
                }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, error = result.message) }
            }
        }
    }

    fun dismissMatch() {
        _uiState.update { it.copy(match = null) }
        advance()
    }

    private fun advance() {
        _uiState.update { state -> state.copy(index = state.index + 1) }
        // Fetch more when nearing the end of the loaded page.
        if (_uiState.value.index >= _uiState.value.cards.size - 3 && _uiState.value.cards.isNotEmpty()) {
            fetchMore()
        }
    }

    private fun fetchMore() {
        if (_uiState.value.refreshing) return
        _uiState.update { it.copy(refreshing = true) }
        viewModelScope.launch {
            val offset = _uiState.value.cards.size
            when (val result = discoveryRepository.feed(limit = pageLimit, offset = offset)) {
                is ApiResult.Success -> _uiState.update { state ->
                    val existing = state.cards.map { it.userId }.toSet()
                    val fresh = result.data.filterNot { it.userId in existing }
                    state.copy(refreshing = false, cards = state.cards + fresh)
                }
                is ApiResult.Error -> _uiState.update { it.copy(refreshing = false) }
            }
        }
    }
}
