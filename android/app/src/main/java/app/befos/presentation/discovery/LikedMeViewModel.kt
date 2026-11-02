package app.befos.presentation.discovery

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.core.network.BROKEN_PAGE_LINK_CODE
import app.befos.domain.model.IncomingLike
import app.befos.presentation.common.PageWalk
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
     * The server stopped at its page and said more taps stand behind it. Without this line the list
     * would claim it named everyone who ever tapped, which is the one thing it cannot know.
     */
    val truncated: Boolean = false,
    /**
     * The link the last answer handed out, and the only thing that reaches the taps behind it. Null
     * means the walk is over: the server said nothing stands beyond the rows this screen holds.
     */
    val nextCursor: String? = null,
    /** How many pages the reader has turned through, counting the first one. */
    val pages: Int = 0,
    /** The next page is on the wire; the rows already shown stay on screen while it waits. */
    val loadingMore: Boolean = false,
    /**
     * A page behind the first one failed. Kept apart from [error] on purpose: the taps above are real
     * and still drawn, and a full-screen failure would say the inbox could not be read when only its
     * older half did not come.
     */
    val moreError: String? = null,
    /**
     * The envelope's machine code behind [moreError], kept because the two repairs differ. A dead
     * link is not retried — it is dropped, and the screen re-reads the newest page; a page that only
     * failed to arrive is asked for again by the same key.
     */
    val moreErrorCode: String = "",
    val busy: Boolean = false,
    val error: String? = null,
    /**
     * A match the like-back just formed, so the screen can offer the pair instead of leaving the
     * person wondering why the row vanished.
     */
    val match: MatchedMoment? = null,
) {
    val isEmpty: Boolean get() = !loading && error == null && likes.isEmpty()

    /**
     * More taps exist, nothing is already asking for them, and the walk was not stopped by a refusal.
     *
     * The last clause is the rule stage 123 learned on a device with the database down: a gate that
     * only looks at `nextCursor != null` lets the trigger at the bottom of a list knock forever, and
     * the reader can neither learn that the page failed nor ask for it themselves. An automatic walk
     * stops at the first refusal; repeating it is the verb on the notice.
     */
    val canLoadMore: Boolean
        get() = nextCursor != null &&
            !loadingMore && !loading && !busy && error == null && moreError == null

    /** The same facts every paged list hands the shared tail resolver. */
    fun walk(): PageWalk = PageWalk(
        loadingMore = loadingMore,
        moreError = moreError,
        moreErrorCode = moreErrorCode,
        truncated = truncated,
        nextCursor = nextCursor,
        pages = pages,
    )
}

// The row staying put is what the person has to see: a transport line alone describes a socket,
// while this sentence says the tap is still here and the answer was not recorded.
private const val ANSWER_NOT_RECORDED = "Ответ не записан — лайк остался в списке."

/**
 * The account's own read of who tapped it, and the walk from one page of that inbox to the next.
 *
 * One request paints the first page and hands over the key to the rest of it. Stage 112 opened this
 * door, stage 113 priced it, and until stage 126 it answered fifty taps and stopped: the screen could
 * say «за ними ждут другие» and had no verb for reaching them. The stand says how much of an inbox
 * that left unread — 98 / 994 / 4 994 incoming taps for one reader at its three scales.
 *
 * Nothing is polled — a tap that arrives while this screen is open waits for the retry the notice
 * offers, exactly like a chat line does elsewhere in the app. A row the reader answers leaves the list
 * by the server's own write, and the walk keeps its place: the frontier is a moment and a row id, not
 * a count, so a row that went from behind does not move the pages in front of it.
 */
class LikedMeViewModel(
    private val discoveryRepository: DiscoveryRepository,
    private val answeredUsers: AnsweredUsers,
) : ViewModel() {

    private val _uiState = MutableStateFlow(LikedMeUiState())
    val uiState: StateFlow<LikedMeUiState> = _uiState.asStateFlow()

    /**
     * Есть ли на проводе чтение. Полю `loading` для этого доверия нет: начальное состояние стоит на
     * `loading = true` ещё до первого обращения, и проверка по нему отменила бы то самое чтение,
     * которое делает `init`.
     */
    private var readOnTheWire = false

    init {
        load()
    }

    fun load() {
        if (readOnTheWire) return
        readOnTheWire = true
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            val result = discoveryRepository.likedMe(null)
            // Снимается до, а не внутри `update`: блок обновления StateFlow перепускается, если с
            // состоянием в этот момент работал кто-то ещё.
            readOnTheWire = false
            when (result) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loading = false,
                        likes = result.data.likes,
                        truncated = result.data.truncated,
                        nextCursor = result.data.nextCursor,
                        pages = 1,
                        loadingMore = false,
                        moreError = null,
                        moreErrorCode = "",
                        error = null,
                    )
                }
                // The rows stay — one failed refresh does not unmake the taps other people made — but
                // the frontier goes with the page this read was replacing: a link left from an earlier
                // walk is a key into a list this screen has just failed to re-read.
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        loading = false,
                        loadingMore = false,
                        error = result.message,
                        nextCursor = null,
                        moreError = null,
                        moreErrorCode = "",
                    )
                }
            }
        }
    }

    /**
     * Turn the page. What is on the screen stays on it while the next page is on the wire, and a page
     * that does not come leaves it there: an older half of the inbox failing to arrive does not unmake
     * the half that did.
     */
    fun loadMore() {
        val state = _uiState.value
        val cursor = state.nextCursor ?: return
        // Не `canLoadMore`: та же строка закрывает автоматический обход после отказа, а здесь стоит
        // человек с «Повторить» в руках — для него отказ не причина молчать.
        if (state.busy || state.loadingMore || state.loading || state.error != null) return
        _uiState.update { it.copy(loadingMore = true, moreError = null, moreErrorCode = "") }
        viewModelScope.launch {
            when (val result = discoveryRepository.likedMe(cursor)) {
                is ApiResult.Success -> _uiState.update { current ->
                    val held = current.likes.map { it.userId }.toSet()
                    current.copy(
                        // A person the server names twice enters the list once: a tap that was taken
                        // back and given again between two pages writes a fresh row, and showing the
                        // same face twice would be this screen's bug rather than the door's.
                        likes = current.likes + result.data.likes.filter { it.userId !in held },
                        truncated = result.data.truncated,
                        nextCursor = result.data.nextCursor,
                        pages = current.pages + 1,
                        loadingMore = false,
                        moreError = null,
                        moreErrorCode = "",
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loadingMore = false, moreError = result.message, moreErrorCode = result.errorCode)
                }
            }
        }
    }

    /**
     * The verb on the notice under a failed page, and the reason [LikedMeUiState.moreErrorCode] exists.
     *
     * A page that simply did not arrive is asked for again with the same key. A key the server refuses
     * is a different case: the frontier it names is gone — walked past, aged out, or sealed by a key
     * this deployment no longer holds — and the only honest ask is the newest page, so the dead link is
     * dropped first and the list is read from the top. Repeating a refused link would be this screen
     * knocking on a door it has just been told is not there.
     */
    fun retryMore() {
        if (_uiState.value.moreErrorCode == BROKEN_PAGE_LINK_CODE) load() else loadMore()
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
