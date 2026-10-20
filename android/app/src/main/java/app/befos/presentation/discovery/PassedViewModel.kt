package app.befos.presentation.discovery

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.PassedUser
import app.befos.domain.repository.DiscoveryRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PassedUiState(
    val loading: Boolean = true,
    val passed: List<PassedUser> = emptyList(),
    /**
     * The server stopped at fifty answers and said more stand behind them. Without this line the list
     * would claim it named every person the account ever passed, which is the one thing it cannot know.
     */
    val truncated: Boolean = false,
    val busy: Boolean = false,
    val error: String? = null,
    /**
     * Whose answer is being taken back, so the row can be named in the notice the write leaves
     * behind. The name comes from the row the server listed, never from a cached profile.
     */
    val released: String? = null,
) {
    val isEmpty: Boolean get() = !loading && error == null && passed.isEmpty()
}

// The row staying put is the honest part of a failed release: a transport line alone would describe
// a socket, while this says the answer is still written and the person is still out of the deck.
private const val RELEASE_NOT_RECORDED = "Возврат не записан — человек остался в списке."

/**
 * The account's own read of the cards it passed, and the one verb that takes an answer back.
 *
 * One request paints the page. A release replaces it with the server's answer rather than subtracting
 * the tapped row locally, because the write and the read are the same question: a person the server
 * still holds has to stay visible with a working tap. The deck is deliberately not told about a
 * release — the returned person cannot rejoin the page already in memory, since ranks are assigned
 * once and a release re-queues through the normal refill, so the deck meets them on its own next
 * load and the screen says so instead of promising them at the front.
 */
class PassedViewModel(
    private val discoveryRepository: DiscoveryRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PassedUiState())
    val uiState: StateFlow<PassedUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.passed()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loading = false,
                        passed = result.data.passed,
                        truncated = result.data.truncated,
                        error = null,
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loading = false, error = result.message)
                }
            }
        }
    }

    /**
     * Take one pass back. The person leaves this list because the server said so, and the notice
     * names them: the row is gone from the screen the moment the write lands, and a message that
     * pointed at nobody would leave the reader wondering whether the tap did anything at all.
     *
     * A refusal — an answer already taken back, an account that has gone — leaves the list exactly as
     * it stood and says what the server said, rather than hiding a row that is still written.
     */
    fun release(userId: String) {
        if (_uiState.value.busy) return
        val name = _uiState.value.passed.firstOrNull { it.userId == userId }?.name
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.unpass(userId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        busy = false,
                        passed = result.data.passed,
                        truncated = result.data.truncated,
                        error = null,
                        released = name,
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(busy = false, error = "$RELEASE_NOT_RECORDED ${result.message}")
                }
            }
        }
    }

    /** The notice has been read; the row it named is already gone from the list. */
    fun dismissReleased() {
        _uiState.update { it.copy(released = null) }
    }
}
