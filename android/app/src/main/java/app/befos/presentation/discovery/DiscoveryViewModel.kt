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
    /**
     * The next page of the deck did not arrive. The cards already loaded stay swipeable, so
     * [error] would be wrong; without this line the deck simply runs out and claims it showed
     * everyone.
     */
    val feedError: String? = null,
    val match: LikeOutcome? = null,
) {
    val current: DiscoveryCard? get() = cards.getOrNull(index)
    val isEmpty: Boolean get() = !loading && cards.isEmpty()
}

class DiscoveryViewModel(private val discoveryRepository: DiscoveryRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(DiscoveryUiState())
    val uiState: StateFlow<DiscoveryUiState> = _uiState.asStateFlow()

    private val pageLimit = 20

    // The deck is ranked on the server and paged by cursor, so the client carries the
    // cursor instead of a position: a swipe changes how many cards remain, never where the
    // next card is.
    private var cursor: String? = null
    private var moreComing = true

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null, feedError = null) }
        cursor = null
        moreComing = true
        viewModelScope.launch {
            when (val result = discoveryRepository.feed(limit = pageLimit, cursor = null)) {
                is ApiResult.Success -> {
                    val page = result.data
                    // The first page hands over the cursor the rest of the deck continues
                    // from; dropping it would ask for this page again and append it twice.
                    cursor = page.nextCursor
                    moreComing = page.hasMore
                    _uiState.update {
                        it.copy(loading = false, cards = page.cards, index = 0)
                    }
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

    /**
     * Ask for the page after the one on screen. Public because the screen offers it as the
     * retry for a page that did not arrive.
     */
    fun fetchMore() {
        if (_uiState.value.refreshing || !moreComing) return
        _uiState.update { it.copy(refreshing = true) }
        val from = cursor
        viewModelScope.launch {
            when (val result = discoveryRepository.feed(limit = pageLimit, cursor = from)) {
                is ApiResult.Success -> {
                    val page = result.data
                    cursor = page.nextCursor ?: from
                    moreComing = page.hasMore
                    _uiState.update { state ->
                        state.copy(refreshing = false, cards = state.cards + page.cards, feedError = null)
                    }
                }
                // A failed page keeps the cursor where it was: the next attempt asks for
                // the same page again rather than skipping past cards it never showed.
                is ApiResult.Error -> _uiState.update {
                    it.copy(refreshing = false, feedError = result.message)
                }
            }
        }
    }
}
