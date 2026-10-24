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
     * The server stopped at its page and said more taps stand behind what this screen holds. Without
     * this line the list would claim it named every person the account ever liked, which is the one
     * thing it cannot know.
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
     * A page behind the first one failed. It is kept apart from [error] on purpose: the rows above are
     * real and still drawn, and a full-screen failure would say the account's history could not be read
     * when only its older half did not come.
     */
    val moreError: String? = null,
    val busy: Boolean = false,
    /** The row whose withdrawal is on the wire, so that one card can say so while the others stand. */
    val withdrawing: String? = null,
    val error: String? = null,
    /**
     * What the server said about a write this screen asked for and it refused.
     *
     * Kept apart from [error] because the two words answer different questions: [error] means the
     * account's history could not be read, and this means one gesture did not land while the history
     * above it was read perfectly well. Until stage 123 a refused withdrawal went into the read channel,
     * and the screen answered a tap the server declined by replacing the rows the reader holds with
     * «Не удалось прочитать ваши лайки» — a card whose only verb re-read a page that had never stopped
     * answering.
     */
    val writeError: String? = null,
    /** The row a refusal belongs to: the notice's «Повторить» repeats that gesture, not a fresh read. */
    val withdrawFailed: String? = null,
    val withdrawn: String? = null,
) {
    val isEmpty: Boolean get() = !loading && error == null && likes.isEmpty()

    /**
     * More taps exist, nothing is already on the wire asking for them, and the walk was not stopped by
     * a refusal.
     *
     * The last clause is the whole point. On a device, with the database down, the door answered this
     * page 503 in four seconds; the gate still read `nextCursor != null`, so the trigger at the bottom
     * of the list asked again, and again, and again — the tail held «Догружаю ваши касания…» for the
     * whole five minutes of that walk and never showed the notice with «Повторить», while the reader
     * could neither learn that the page had failed nor ask for it themselves. An automatic walk stops at
     * the first refusal; repeating it is the verb on the notice, and that verb goes through [loadMore].
     *
     * A withdrawal on the wire closes the gate for the same reason the walk closes at a refusal: the
     * write's answer describes the list after the row left it, and a page that started before that
     * answer would be appended to a list the write had already replaced.
     */
    val canLoadMore: Boolean
        get() = nextCursor != null &&
            !loadingMore && !loading && !busy && error == null && moreError == null
}

// The row staying put is the honest part of a failed withdrawal: a transport line alone would describe
// a socket, while this says the tap is still written and the person is still in this list.
private const val WITHDRAW_NOT_RECORDED = "Лайк не отозван — человек остался в списке."

/**
 * The account's own read of the taps it left standing, the verb that takes a tap back, and the walk
 * from one page of that history to the next.
 *
 * One request paints the first page and hands over the key to the rest of it. Stage 116 shipped this
 * screen knowing the list was longer than the page — the server said `has_more` and the client wrote
 * «за ними ждут другие» — and unable to do anything about it, because the door took no cursor. The page
 * count in [MyLikesUiState.pages] is what that gap looked like from the device: fifty rows, and the
 * account's own history stopping there. The stand names the size of it: 87 / 893 / 4 493 outgoing taps
 * at the three scales its table publishes.
 *
 * A withdrawal replaces the page with the server's answer rather than removing the tapped row locally,
 * because the write and the read are the same question: a person the server still holds has to stay
 * visible with a working tap. Once the reader has turned past the first page the answer describes a
 * page they have already walked through, so the row this write removed leaves the list and the reader's
 * own frontier stays where they put it — the server's link is keyed to a moment, not to a row count, so
 * a row that went from behind does not move the pages in front of it.
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

    /**
     * Есть ли на проводе чтение. Полю `loading` для этого доверия нет: начальное состояние стоит на
     * `loading = true` ещё до первого обращения, и проверка по нему отменила бы то самое чтение,
     * которое делает `init`. Оба ответа чтения — и успех, и отказ — снимают этот флаг, поэтому
     * переживает он только отмену самой модели.
     */
    private var readOnTheWire = false

    init {
        load()
    }

    /**
     * Read the account's taps from the newest page.
     *
     * One read at a time, and none over a write that is still on the wire: an answer to a read started
     * before a withdrawal would put back the row the notice above the list has just named as gone, and
     * the person would watch a tap they took back come back on its own.
     */
    fun load() {
        if (readOnTheWire || _uiState.value.busy) return
        readOnTheWire = true
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            val result = discoveryRepository.liked(null)
            // Снимается до, а не внутри `update`: блок обновления StateFlow перепускается, если с
            // состоянием в этот момент работал кто-то ещё, и флаг снялся бы столько раз, сколько
            // перепустился цикл.
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
                        error = null,
                        writeError = null,
                        withdrawFailed = null,
                    )
                }
                // The rows stay where they are — one failed refresh does not unmake the taps the account
                // made — but the frontier goes with the page this read was replacing. A cursor left from
                // an earlier walk would be a link into a list this screen has just failed to re-read, and
                // «Показать ещё» would hand a door a key it no longer matches. The page count is kept:
                // the rows on the screen still came from that many pages, and a withdrawal decides by it
                // whether the write's answer is the list or just the row that left.
                //
                // What the last answer that did come said about the rest of the list is kept too. A
                // reload that failed does not unmake «ваших касаний больше» — and clearing it here made
                // the tail below print «Дальше ваших касаний нет» and the counter «весь список» over a
                // history this account had not finished reading. The refusal of a page goes with the key
                // that page needed: without a cursor there is no page to repeat, and the sentence above
                // the rows already names the read that did not come.
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        loading = false,
                        loadingMore = false,
                        error = result.message,
                        nextCursor = null,
                        moreError = null,
                    )
                }
            }
        }
    }

    /**
     * Turn the page. The rows already on screen stay there while the next page is on the wire, and a
     * page that does not come leaves them: the account's history is not unmade by one failed read of its
     * older half, and the notice with «Повторить» is what says which part is missing.
     *
     * A person who taps the same row twice, or scrolls to the end twice before the first answer lands,
     * gets one request — [MyLikesUiState.canLoadMore] is false while a page is out, and the guard is
     * read once before the coroutine starts rather than after it resumes.
     *
     * A withdrawal on the wire stops a page too. The write's answer describes the list as it is after
     * the row left it; a page that started before the write and lands after it would append rows onto
     * a list the write had already replaced, and the person would see the tap they took back again.
     */
    fun loadMore() {
        val state = _uiState.value
        val cursor = state.nextCursor ?: return
        // Не `canLoadMore`: та же строка закрывает автоматический обход после отказа, а здесь стоит
        // человек с «Повторить» в руках — для него отказ не причина молчать.
        if (state.busy || state.loadingMore || state.loading || state.error != null) return
        _uiState.update { it.copy(loadingMore = true, moreError = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.liked(cursor)) {
                is ApiResult.Success -> _uiState.update { current ->
                    val page = result.data
                    val held = current.likes.map { it.userId }.toSet()
                    // A row the server names twice enters the list once. The keyset cannot repeat a
                    // gesture on its own, but a person who liked somebody again between two pages wrote
                    // a fresh row, and a list that showed the same face twice would be this screen's
                    // bug rather than the server's.
                    current.copy(
                        likes = current.likes + page.likes.filter { it.userId !in held },
                        truncated = page.truncated,
                        nextCursor = page.nextCursor,
                        pages = current.pages + 1,
                        loadingMore = false,
                        moreError = null,
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loadingMore = false, moreError = result.message)
                }
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
        if (_uiState.value.busy || _uiState.value.loading || _uiState.value.loadingMore) return
        val name = _uiState.value.likes.firstOrNull { it.userId == userId }?.name
        _uiState.update {
            it.copy(busy = true, withdrawing = userId, error = null, writeError = null, withdrawFailed = null)
        }
        viewModelScope.launch {
            when (val result = discoveryRepository.unlike(userId)) {
                is ApiResult.Success -> _uiState.update { current ->
                    if (current.pages <= 1) {
                        // The screen is holding the page the write answered, so the answer is the list —
                        // and with it the page refusal: this answer names where the list ends now, and a
                        // notice about a page that did not come would be standing over a cursor it can no
                        // longer use, offering «Повторить» to a walk that has nothing left to repeat.
                        current.copy(
                            busy = false,
                            withdrawing = null,
                            likes = result.data.likes,
                            truncated = result.data.truncated,
                            nextCursor = result.data.nextCursor,
                            moreError = null,
                            error = null,
                            withdrawn = name,
                        )
                    } else {
                        // Deeper than the first page, the answer describes rows this reader has walked
                        // past. Adopting it would drop the older half of the list the server still holds
                        // and move the frontier back to the top; the row this write removed leaves, and
                        // the rest of the walk stays where the reader left it.
                        current.copy(
                            busy = false,
                            withdrawing = null,
                            likes = current.likes.filter { it.userId != userId },
                            error = null,
                            withdrawn = name,
                        )
                    }
                }
                // The write channel, not the read one: the rows this screen holds were read, and they stay
                // drawn with the sentence about the one gesture that did not land above them. The row the
                // refusal belongs to is kept with it, because the notice's «Повторить» has to repeat that
                // tap — answering a refused write by re-reading the list would replace a page the server
                // never stopped giving and leave the reader looking for the row again.
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        busy = false,
                        withdrawing = null,
                        writeError = "$WITHDRAW_NOT_RECORDED ${result.message}",
                        withdrawFailed = userId,
                    )
                }
            }
        }
    }

    /** The notice has been read; the row it named is already gone from the list. */
    fun dismissWithdrawn() {
        _uiState.update { it.copy(withdrawn = null) }
    }
}
