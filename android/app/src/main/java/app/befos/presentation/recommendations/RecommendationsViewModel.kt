package app.befos.presentation.recommendations

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Recommendation
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.MatchRepository
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

private const val SEND_SENTENCE = "Не удалось отправить предложение."
private const val RECORD_SENTENCE = "Идея отправлена в чат, но отметить её в паре не удалось."
private const val DECLINE_SENTENCE = "Не удалось отклонить идею."
private const val RESTORE_SENTENCE = "Не удалось вернуть идею в подборку."
// Two sentences rather than one: naming an hour and agreeing to one are different answers to the
// pair, and a refusal of the second one did not go near the first.
private const val OFFER_SENTENCE = "Не удалось предложить время."
private const val ACCEPT_SENTENCE = "Не удалось подтвердить время."

private fun reasonSentence(sentence: String, reason: String?) =
    if (reason == null) sentence else "$sentence $reason"

data class RecommendationsUiState(
    val loading: Boolean = true,
    val items: List<Recommendation> = emptyList(),
    val selected: Set<Int> = emptySet(),
    // Ideas this person pushed away. The page still carries them, because a refusal edits only
    // their own list rather than deleting a record: the screen shows them as a section with
    // «Вернуть», and the idea behind them stays readable with the reason it was chosen for.
    val declined: Set<Int> = emptySet(),
    val error: String? = null,
    val selectError: String? = null,
    val declineError: String? = null,
    // Ideas the pair can already read in chat whose mark the server refused. They are the
    // ones a repeated visit would offer a second time, so the tab has to keep them named.
    val unsavedChoices: Set<Int> = emptySet(),
    // Hours this person named and the page has not reported back yet, and the plan the pair has
    // once one half agreed to the other's. Keyed by the card, because a time belongs to one idea:
    // a card that lost its own hour must not go on showing another one's plan.
    val myOffers: Map<Int, String> = emptyMap(),
    val agreedMoments: Map<Int, String> = emptyMap(),
    // Why this card's last time tap did not land. One line per card rather than one above the
    // list: an hour the server refused for кино says nothing about настольные игры, and a shared
    // notice would have to name the card it belongs to anyway.
    val timeErrors: Map<Int, String> = emptyMap(),
)

class RecommendationsViewModel(
    private val matchRepository: MatchRepository,
    private val chatRepository: ChatRepository,
    private val matchId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(RecommendationsUiState())
    val uiState: StateFlow<RecommendationsUiState> = _uiState.asStateFlow()

    private val pendingProposalIds = mutableMapOf<String, String>()

    // Refusals whose answer has not arrived yet, and which way each was going: true pushed the
    // card away, false took it back. A page that lands mid-flight cannot know either.
    private val pendingRefusals = mutableMapOf<Int, Boolean>()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = matchRepository.recommendations(matchId)) {
                is ApiResult.Success -> _uiState.update { state ->
                    val cards = result.data.sortedBy { r -> r.position }
                    val recorded = cards.filter { it.selected }.map { it.activity.id }.toSet()
                    // A page that reports the mark resolves the doubt the notice was raising;
                    // local marks are kept because a tap in flight is not on the server yet.
                    val left = state.unsavedChoices - recorded
                    val refused = cards.filter { it.declined }.map { it.activity.id }.toSet()
                    val pushedAway = pendingRefusals.filterValues { push -> push }.keys
                    val takingBack = pendingRefusals.filterValues { push -> !push }.keys
                    // The hours the page carries. A read that landed mid-write has no hour yet, so
                    // what the person named locally is kept instead of being cleared by the page.
                    val reportedOffers = cards.mapNotNull { r -> r.myMeetingTime?.let { r.activity.id to it } }.toMap()
                    val reportedPlans = cards.mapNotNull { r -> r.agreedTime?.let { r.activity.id to it } }.toMap()
                    state.copy(
                        loading = false,
                        items = cards,
                        selected = state.selected + recorded,
                        unsavedChoices = left,
                        declined = (refused + pushedAway) - takingBack,
                        selectError = state.selectError.takeUnless {
                            left.isEmpty() && it?.startsWith(RECORD_SENTENCE) == true
                        },
                        myOffers = reportedOffers + state.myOffers,
                        agreedMoments = reportedPlans + state.agreedMoments,
                        // A page that shows the plan ends the doubt about it; the agreement is on the
                        // pair now, so there is nothing left for the person to retry.
                        timeErrors = state.timeErrors - reportedPlans.keys,
                    )
                }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    fun select(activityId: Int, title: String) {
        if (_uiState.value.selected.contains(activityId)) return
        val key = activityId.toString()
        // A tap that got no answer may still have stored the proposal, so the retry keeps
        // its name and the pair reads one idea instead of two identical ones. An answered
        // tap ends the name: the next proposal of this activity is a new intent.
        val clientMsgId = pendingProposalIds.getOrPut(key) { UUID.randomUUID().toString() }
        _uiState.update {
            // The notice of an older idea whose record is still missing survives this tap: that
            // condition did not go away, and a second failure sentence would overwrite it anyway.
            it.copy(
                selected = it.selected + activityId,
                selectError = it.selectError.takeIf { error ->
                    error?.startsWith(RECORD_SENTENCE) == true && it.unsavedChoices.isNotEmpty()
                },
            )
        }
        viewModelScope.launch {
            // Titles are noun phrases ("Вечер настольных игр"), so the frame must not add a verb.
            // Whose idea this is second decides the sentence: the page says whether the partner has
            // already put this card into the chat, and a tap on a card they proposed is an answer to
            // it, not a copy of it.
            val partnerProposed = _uiState.value.items
                .any { it.activity.id == activityId && it.partnerSelected }
            val body = if (partnerProposed) "Я тоже за: $title." else "Идея для нас: $title. Что скажете?"
            when (val result = chatRepository.send(matchId, body, clientMsgId)) {
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        selected = it.selected - activityId,
                        selectError = reasonSentence(SEND_SENTENCE, result.message),
                    )
                }
                is ApiResult.Success -> {
                    pendingProposalIds.remove(key)
                    // The record the next page reads back is written here; the local mark above
                    // is what the same visit to the tab shows before that answer arrives.
                    when (val recorded = matchRepository.selectRecommendation(matchId, activityId)) {
                        is ApiResult.Error -> markUnsaved(activityId, recorded.message)
                        is ApiResult.Success -> clearUnsaved(activityId)
                    }
                }
            }
        }
    }

    /** Re-sends only the marks the pair is missing; the chat message of these ideas is already out. */
    fun retryRecords() {
        val pending = _uiState.value.unsavedChoices
        if (pending.isEmpty()) return
        viewModelScope.launch {
            var failure: String? = null
            pending.forEach { id ->
                when (val result = matchRepository.selectRecommendation(matchId, id)) {
                    is ApiResult.Error -> failure = result.message
                    is ApiResult.Success -> clearUnsaved(id)
                }
            }
            if (failure != null && _uiState.value.unsavedChoices.isNotEmpty()) {
                _uiState.update { it.copy(selectError = reasonSentence(RECORD_SENTENCE, failure)) }
            }
        }
    }

    /** Push an idea out of this person's own list. Nothing leaves the device but the mark. */
    fun decline(activityId: Int) {
        if (_uiState.value.declined.contains(activityId)) return
        pendingRefusals[activityId] = true
        _uiState.update { it.copy(declined = it.declined + activityId, declineError = null) }
        viewModelScope.launch {
            when (val result = matchRepository.declineRecommendation(matchId, activityId)) {
                // A proposal can half-succeed — the chat has the message while the pair's record
                // does not — so a failed mark stays named as a debt. A refusal sends nothing to
                // the chat: a write that failed is simply not a refusal, and the card comes back
                // to the list the person just left it out of, where the tap can be made again.
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        declined = it.declined - activityId,
                        declineError = reasonSentence(DECLINE_SENTENCE, result.message),
                    )
                }
                is ApiResult.Success -> Unit
            }
            pendingRefusals.remove(activityId)
        }
    }

    /** Put a pushed-away idea back; the refusal is the person's own, so this is theirs to undo. */
    fun restore(activityId: Int) {
        if (!_uiState.value.declined.contains(activityId)) return
        pendingRefusals[activityId] = false
        _uiState.update { it.copy(declined = it.declined - activityId, declineError = null) }
        viewModelScope.launch {
            when (val result = matchRepository.restoreRecommendation(matchId, activityId)) {
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        declined = it.declined + activityId,
                        declineError = reasonSentence(RESTORE_SENTENCE, result.message),
                    )
                }
                is ApiResult.Success -> Unit
            }
            pendingRefusals.remove(activityId)
        }
    }

    /**
     * Name — or move — the hour this person would meet at for this idea.
     *
     * No idempotency key, unlike a chat send: the pair holds one row per person per card and this
     * route replaces the hour on it, so a tap whose answer never arrived is repeated as the same
     * hour rather than as a second offer the partner would have to choose between.
     */
    fun proposeTime(activityId: Int, whenIso: String) {
        val previous = _uiState.value.myOffers[activityId]
        _uiState.update {
            it.copy(
                myOffers = it.myOffers + (activityId to whenIso),
                timeErrors = it.timeErrors - activityId,
            )
        }
        viewModelScope.launch {
            when (val result = matchRepository.proposeMeetingTime(matchId, activityId, whenIso)) {
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        // Back to the hour this person had named before this tap, not to nothing: an
                        // offer that was moved and refused still stands where it stood.
                        myOffers = previous?.let { was -> it.myOffers + (activityId to was) }
                            ?: (it.myOffers - activityId),
                        timeErrors = it.timeErrors + (activityId to reasonSentence(OFFER_SENTENCE, result.message)),
                    )
                }
                is ApiResult.Success -> Unit
            }
        }
    }

    /**
     * Agree to the hour the other half named. The instant goes back as this card read it, so an
     * offer that moved in the meantime is refused by the server instead of being agreed to silently.
     */
    fun acceptTime(activityId: Int, whenIso: String) {
        if (_uiState.value.agreedMoments.containsKey(activityId)) return
        _uiState.update {
            it.copy(
                agreedMoments = it.agreedMoments + (activityId to whenIso),
                timeErrors = it.timeErrors - activityId,
            )
        }
        viewModelScope.launch {
            when (val result = matchRepository.acceptMeetingTime(matchId, activityId, whenIso)) {
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        agreedMoments = it.agreedMoments - activityId,
                        timeErrors = it.timeErrors + (activityId to reasonSentence(ACCEPT_SENTENCE, result.message)),
                    )
                }
                // The pair has a plan from this answer, so the card shows the plan; an hour this
                // person named earlier stays on the row as its own fact, not as a rival offer.
                is ApiResult.Success -> Unit
            }
        }
    }

    private fun markUnsaved(activityId: Int, reason: String) {
        _uiState.update {
            it.copy(
                unsavedChoices = it.unsavedChoices + activityId,
                selectError = reasonSentence(RECORD_SENTENCE, reason),
            )
        }
    }

    private fun clearUnsaved(activityId: Int) {
        _uiState.update {
            val left = it.unsavedChoices - activityId
            it.copy(
                unsavedChoices = left,
                selectError = it.selectError.takeUnless { error ->
                    left.isEmpty() && error?.startsWith(RECORD_SENTENCE) == true
                },
            )
        }
    }
}
