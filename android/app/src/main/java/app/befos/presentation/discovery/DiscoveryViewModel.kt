package app.befos.presentation.discovery

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.DiscoveryCard
import app.befos.domain.model.DiscoveryEmpty
import app.befos.domain.model.LikeOutcome
import app.befos.domain.model.WaitlistStatus
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.repository.ReferralRepository
import app.befos.domain.repository.SafetyRepository
import app.befos.domain.safety.AnsweredUsers
import app.befos.presentation.common.ReportForm
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
    /**
     * The card whose like or pass the server refused. The fling animation runs ahead of the write
     * and carries the card off the screen, so the screen needs to know which one to bring back;
     * without it the deck shows an empty area, a counter that did not move, and a notice that
     * describes a socket instead of the person still sitting there.
     */
    val rejectedCard: String? = null,
    /**
     * The server's own sentence about why a page carried no cards. Null for a deck that has cards
     * and for an older server that does not explain itself; the screen then falls back to the
     * honest «пока новых анкет нет» rather than guessing a reason it cannot see.
     */
    val empty: DiscoveryEmpty? = null,
    /** The reader's waiting mark as the server answered it last, not as this screen hopes. */
    val waitlist: WaitlistStatus? = null,
    val waitlistBusy: Boolean = false,
    /** A failed waitlist write. It lives here so it cannot replace the deck's state with an error. */
    val waitlistError: String? = null,
) {
    val current: DiscoveryCard? get() = cards.getOrNull(index)
    val isEmpty: Boolean get() = !loading && cards.isEmpty()

    /**
     * Every card this visit received was answered, no page is in flight, and none failed.
     *
     * This is a client observation outright, never a server reason: it can say «вы посмотрели всё,
     * что пришло сейчас», and it must not say «в BeFoS больше никого нет». The server's own reason
     * (if any) rides beside it and takes the screen first; the fallback copy is the client's.
     */
    val reviewedAllLoaded: Boolean
        get() = !loading && !refreshing && current == null && cards.isNotEmpty() && feedError == null
}

// The transport line on its own quotes a failure the viewer cannot act on: naming the card that
// returns is what tells them the answer was not counted.
private const val ANSWER_NOT_RECORDED = "Ответ не записан — карточка вернулась."

class DiscoveryViewModel(
    private val discoveryRepository: DiscoveryRepository,
    safetyRepository: SafetyRepository,
    answeredUsers: AnsweredUsers,
    private val referralRepository: ReferralRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(DiscoveryUiState())
    val uiState: StateFlow<DiscoveryUiState> = _uiState.asStateFlow()

    /**
     * The complaint form, the same one the profile screen and a conversation render. A card is the
     * one place a person is seen without their profile being opened, and until stage 102 the only way
     * to complain about them was to open the profile and find the flag there.
     */
    val report = ReportForm(safetyRepository, viewModelScope)

    private val pageLimit = 20

    // The deck is ranked on the server and paged by cursor, so the client carries the
    // cursor instead of a position: a swipe changes how many cards remain, never where the
    // next card is.
    private var cursor: String? = null
    private var moreComing = true

    init {
        load()
        viewModelScope.launch {
            answeredUsers.answered.collect(::forget)
        }
    }

    /**
     * Drop a card the viewer answered on the profile screen.
     *
     * The page in memory knows nothing about a like, a pass or a block performed there, so
     * without this the person you just blocked comes back as the next card.
     */
    private fun forget(userId: String) {
        _uiState.update { state ->
            val position = state.cards.indexOfFirst { it.userId == userId }
            if (position < 0) return@update state
            state.copy(
                cards = state.cards.filterNot { it.userId == userId },
                // A card removed before the current one shifts it left; the current card
                // being removed means the next one slides into the same slot.
                index = if (position < state.index) state.index - 1 else state.index,
            )
        }
    }

    fun load() {
        _uiState.update {
            it.copy(
                loading = true,
                error = null,
                feedError = null,
                rejectedCard = null,
                empty = null,
                waitlistError = null,
            )
        }
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
                        it.copy(
                            loading = false,
                            cards = page.cards,
                            index = 0,
                            // The server explains a page it could not fill; the screen does not
                            // deduce the reason from the reader's filters on its own.
                            empty = page.empty,
                            waitlist = page.empty?.let { why ->
                                WaitlistStatus(joined = why.waitlistJoined, city = why.waitlistCity)
                            },
                        )
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
                    _uiState.update { it.copy(busy = false, rejectedCard = null) }
                    if (outcome.matched) {
                        _uiState.update { it.copy(match = outcome) }
                    } else {
                        advance()
                    }
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        busy = false,
                        error = "$ANSWER_NOT_RECORDED ${result.message}",
                        rejectedCard = card.userId,
                    )
                }
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
                    _uiState.update { it.copy(busy = false, rejectedCard = null) }
                    advance()
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        busy = false,
                        error = "$ANSWER_NOT_RECORDED ${result.message}",
                        rejectedCard = card.userId,
                    )
                }
            }
        }
    }

    fun dismissMatch() {
        _uiState.update { it.copy(match = null) }
        advance()
    }

    /**
     * Opens the complaint form for the card on screen. The id is taken from the card the person is
     * looking at, here rather than when the form sends: the deck moves on its own once an answer
     * lands, and a complaint written after that would name whoever slid into the slot.
     */
    fun askReport() {
        val card = _uiState.value.current ?: return
        report.open(card.userId)
    }

    /**
     * Closes the form. Nothing else happens: a complaint is not an answer about the person, so the
     * card stays where it was — the viewer still has to like or pass them, and the deck still shows
     * them until one of those is recorded.
     */
    fun closeReport() = report.close()

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
                        val cards = state.cards + page.cards
                        state.copy(
                            refreshing = false,
                            cards = cards,
                            feedError = null,
                            // A next page normally carries cards, and then it carries no
                            // explanation at all. When it answers empty, the explanation stands
                            // for the end the cards already on screen are leading to — so it is
                            // kept rather than dropped, and shown when the last of them is
                            // answered.
                            empty = page.empty,
                            waitlist = page.empty?.let { why ->
                                WaitlistStatus(joined = why.waitlistJoined, city = why.waitlistCity)
                            } ?: state.waitlist,
                        )
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

    /**
     * Leave the voluntary waiting mark.
     *
     * No city is typed here: the server reuses the one on the account's own profile, which keeps
     * this screen from asking for a detail it already has. The mark is not a notification
     * subscription — there is no delivery channel for it yet — so the screen never promises one.
     */
    fun joinWaitlist() {
        if (_uiState.value.waitlistBusy) return
        _uiState.update { it.copy(waitlistBusy = true, waitlistError = null) }
        viewModelScope.launch {
            when (val result = referralRepository.joinWaitlist()) {
                is ApiResult.Success -> _uiState.update { state ->
                    state.copy(
                        waitlistBusy = false,
                        waitlist = result.data,
                        empty = state.empty?.copy(
                            waitlistJoined = result.data.joined,
                            waitlistCity = result.data.city,
                        ),
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(waitlistBusy = false, waitlistError = result.message)
                }
            }
        }
    }

    /** Take the mark back. Idempotent on the server, so a double tap cannot block a later join. */
    fun leaveWaitlist() {
        if (_uiState.value.waitlistBusy) return
        _uiState.update { it.copy(waitlistBusy = true, waitlistError = null) }
        viewModelScope.launch {
            when (val result = referralRepository.leaveWaitlist()) {
                is ApiResult.Success -> _uiState.update { state ->
                    state.copy(
                        waitlistBusy = false,
                        waitlist = WaitlistStatus(joined = false, city = null),
                        empty = state.empty?.copy(waitlistJoined = false, waitlistCity = null),
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(waitlistBusy = false, waitlistError = result.message)
                }
            }
        }
    }

    fun dismissWaitlistError() = _uiState.update { it.copy(waitlistError = null) }
}
