package app.befos.presentation.discovery

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.IncomingLike
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.safety.AnsweredUsers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * The pair a like-back just formed, kept with the words of the row that made it.
 *
 * The row itself leaves the list the moment the server records the answer, so the moment has to
 * carry the name and the photograph with it: a dialog that opened the pair over an empty list
 * would describe a match nobody can see.
 */
data class MatchedMoment(
    val name: String,
    val photoUrl: String?,
    val matchId: String,
    val compatibility: Int?,
)

data class LikedMeUiState(
    val loading: Boolean = true,
    val likes: List<IncomingLike> = emptyList(),
    /**
     * The server stopped at fifty taps and said more wait behind them. Without this line the list
     * would claim it showed everyone who tapped, which is exactly what it cannot know.
     */
    val truncated: Boolean = false,
    val busy: Boolean = false,
    val error: String? = null,
    /**
     * A match the like-back just formed, so the screen can offer the pair instead of leaving the
     * person wondering why the row vanished.
     */
    val match: MatchedMoment? = null,
) {
    val isEmpty: Boolean get() = !loading && error == null && likes.isEmpty()
}

// The row staying put is what the person has to see: a transport line alone describes a socket,
// while this sentence says the tap is still here and the answer was not recorded.
private const val ANSWER_NOT_RECORDED = "Ответ не записан — лайк остался в списке."

/**
 * The account's own read of who tapped it.
 *
 * One request paints the page, and the page is the server's list rather than a copy of the deck in
 * memory: this screen never touched the deck, and a person who taps here writes a like the deck will
 * drop on its own next load. Nothing is polled — a tap that arrives while this screen is open waits
 * for the retry the error row offers, exactly like a chat line does elsewhere in the app.
 */
class LikedMeViewModel(
    private val discoveryRepository: DiscoveryRepository,
    private val answeredUsers: AnsweredUsers,
) : ViewModel() {

    private val _uiState = MutableStateFlow(LikedMeUiState())
    val uiState: StateFlow<LikedMeUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.likedMe()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loading = false,
                        likes = result.data.likes,
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
     * Answer the tap with a tap. The row leaves the list only when the server recorded the like, so
     * a refused write keeps the person visible and the notice says the answer was not counted.
     *
     * The deck is told too: the same person can be waiting there as a card, and a card the account
     * has already liked answers «Профиль не найден» to the tap that follows.
     */
    fun respond(userId: String) {
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.like(userId)) {
                is ApiResult.Success -> {
                    val outcome = result.data
                    val row = _uiState.value.likes.firstOrNull { it.userId == userId }
                    val matchId = outcome.matchId
                    _uiState.update { state ->
                        state.copy(
                            busy = false,
                            error = null,
                            likes = state.likes.filterNot { it.userId == userId },
                            match = if (outcome.matched && row != null && matchId != null) {
                                MatchedMoment(row.name, row.photoUrl, matchId, outcome.compatibility)
                            } else {
                                state.match
                            },
                        )
                    }
                    answeredUsers.publish(userId)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(busy = false, error = "$ANSWER_NOT_RECORDED ${result.message}")
                }
            }
        }
    }

    fun dismissMatch() {
        _uiState.update { it.copy(match = null) }
    }
}
