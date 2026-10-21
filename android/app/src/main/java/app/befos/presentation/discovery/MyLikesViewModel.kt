package app.befos.presentation.discovery

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.OutgoingLike
import app.befos.domain.repository.DiscoveryRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class MyLikesUiState(
    val loading: Boolean = true,
    val likes: List<OutgoingLike> = emptyList(),
    /**
     * The server stopped at fifty taps and said more stand behind them. Without this line the list
     * would claim it named every person the account ever liked, which is the one thing it cannot know.
     */
    val truncated: Boolean = false,
    val busy: Boolean = false,
    val error: String? = null,
    /**
     * Whose tap is being taken back, so the notice can name the person the row was about. The name
     * comes from the row the server listed, never from a cached profile.
     */
    val withdrawn: String? = null,
) {
    val isEmpty: Boolean get() = !loading && error == null && likes.isEmpty()
}

// The row staying put is the honest part of a failed withdrawal: a transport line alone would describe
// a socket, while this says the tap is still written and the person is still in this list.
private const val WITHDRAW_NOT_RECORDED = "Лайк не отозван — человек остался в списке."

/**
 * The account's own read of the taps it left standing, and the one verb that takes a tap back.
 *
 * One request paints the page. A withdrawal replaces it with the server's answer rather than removing
 * the tapped row locally, because the write and the read are the same question: a person the server
 * still holds has to stay visible with a working tap.
 *
 * Nothing is published to the deck's answered-users stream here, and that is the difference between
 * this verb and the inbox's own reply. Answering a tap means the account has spoken about that person,
 * so the deck must not ask again. Taking a tap back means the opposite — the account has unspoken — and
 * the person becomes eligible again, which the deck discovers on its own next refill because the
 * anti-join that excluded them no longer finds a row.
 */
class MyLikesViewModel(
    private val discoveryRepository: DiscoveryRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(MyLikesUiState())
    val uiState: StateFlow<MyLikesUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.liked()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loading = false,
                        likes = result.data.likes,
                        truncated = result.data.truncated,
                        error = null,
                    )
                }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    /**
     * Take one tap back. The person leaves this list because the server said so, and the notice names
     * them: the row is gone from the screen the moment the write lands, and a message that pointed at
     * nobody would leave the reader wondering whether the tap did anything at all.
     *
     * A refusal — a tap already taken back, a person who has gone, a pair the account did not form —
     * leaves the list exactly as it stood and says what the server said, rather than hiding a row that
     * is still written.
     */
    fun withdraw(userId: String) {
        if (_uiState.value.busy) return
        val name = _uiState.value.likes.firstOrNull { it.userId == userId }?.name
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.unlike(userId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        busy = false,
                        likes = result.data.likes,
                        truncated = result.data.truncated,
                        error = null,
                        withdrawn = name,
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(busy = false, error = "$WITHDRAW_NOT_RECORDED ${result.message}")
                }
            }
        }
    }

    /** The notice has been read; the row it named is already gone from the list. */
    fun dismissWithdrawn() {
        _uiState.update { it.copy(withdrawn = null) }
    }
}
