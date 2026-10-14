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
                    state.copy(
                        loading = false,
                        items = cards,
                        selected = state.selected + recorded,
                        unsavedChoices = left,
                        declined = (refused + pushedAway) - takingBack,
                        selectError = state.selectError.takeUnless {
                            left.isEmpty() && it?.startsWith(RECORD_SENTENCE) == true
                        },
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
