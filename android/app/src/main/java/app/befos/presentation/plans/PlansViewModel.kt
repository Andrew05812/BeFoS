package app.befos.presentation.plans

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Plan
import app.befos.domain.repository.ChatEvent
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.PlanRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * The sentence a refused tap starts with, per verb.
 *
 * Kept beside the calls they describe: each of these taps moves a different fact for the pair, so a
 * single «не удалось» would leave the person working out which of the two they just lost.
 */
private object PlanSentences {
    const val ACCEPT = "Не удалось поддержать идею."
    const val DECLINE = "Не удалось отклонить идею."
    const val RESTORE_DECLINE = "Не удалось вернуть идею."
    const val OFFER = "Не удалось предложить время."
    const val CONFIRM = "Не удалось подтвердить время."
    const val CANCEL = "Не удалось отменить план."
    const val RESTORE = "Не удалось вернуть план."
    const val ATTEND = "Не удалось отметить встречу."
    const val UNDO_ATTEND = "Не удалось снять отметку."
    const val WORDS = "Не удалось сохранить слова плана."
}

private fun reasonSentence(sentence: String, reason: String?) =
    if (reason.isNullOrBlank()) sentence else "$sentence $reason"

data class PlansUiState(
    val loading: Boolean = true,
    val plans: List<Plan> = emptyList(),
    val error: String? = null,
    // Said when a plan the pair just moved could not be read back. The rows on the screen are then
    // the ones the socket has already called outdated, and a page that shows them without saying so
    // presents an arrangement the server replaced as the pair's current one.
    val outdated: String? = null,
    // Why the last tap on this plan did not land, one line per plan. A plan is a row the pair reads
    // as its own card, so a refusal says which card it refused rather than floating above the list.
    val tapErrors: Map<String, String> = emptyMap(),
    // Plans whose write has not been answered yet. A card that is busy takes no second tap: two
    // requests for the same verb would ask the pair to say the same thing twice.
    val busy: Set<String> = emptySet(),
)

/** The word the page uses when the plan moved and this copy of the list did not. */
const val PLAN_NOT_CURRENT_WORD = "План пары изменился, а этот список не перечитался."

class PlansViewModel(
    private val planRepository: PlanRepository,
    chatRepository: ChatRepository,
    private val matchId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PlansUiState())
    val uiState: StateFlow<PlansUiState> = _uiState.asStateFlow()

    init {
        load()
        // The pair's hour moves on the other half's screen, and the thread's plan lines are the only
        // notice an open page gets. The page listens to every line the plan wrote rather than to the
        // kinds this build knows: a newer server can move the arrangement with a word this copy has
        // never seen, and a page that did not recognise it would keep showing an hour as current.
        // A sentence somebody typed is not such a notice, and neither is this person's own move — the
        // write below already read the page back for it.
        viewModelScope.launch {
            chatRepository.socket(matchId).collect { event ->
                val line = (event as? ChatEvent.IncomingMessage)?.message ?: return@collect
                if (line.isPlanEvent && !line.isOwn) reread()
            }
        }
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = planRepository.plans(matchId)) {
                // The page is the pair's record, so it ends the doubt a refused write left: the card
                // repaints from what the server says rather than from what this visit tried to do.
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loading = false,
                        plans = result.data,
                        outdated = null,
                        tapErrors = emptyMap(),
                    )
                }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    /**
     * The read a plan line from the other half asks for.
     *
     * It keeps the rows on screen rather than blinking to a skeleton: the pair is reading this page,
     * and trading the arrangement they are looking at for a blank one is not how a move is announced.
     * What it cannot keep is silence — when this read is refused, the rows the pair sees are exactly
     * the ones the socket has already said are not current, so the page names that and waits for the
     * tap that reads again.
     */
    private fun reread() {
        viewModelScope.launch {
            when (val result = planRepository.plans(matchId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(plans = result.data, outdated = null, error = null)
                }
                is ApiResult.Error -> _uiState.update { it.copy(outdated = PLAN_NOT_CURRENT_WORD) }
            }
        }
    }

    fun accept(planId: String) = write(planId, PlanSentences.ACCEPT) { planRepository.accept(planId) }

    fun decline(planId: String) = write(planId, PlanSentences.DECLINE) { planRepository.decline(planId) }

    fun restoreDecline(planId: String) =
        write(planId, PlanSentences.RESTORE_DECLINE) { planRepository.restoreDecline(planId) }

    /** Name — or move — this person's hour. The instant goes out as the hour row chose it. */
    fun offerHour(planId: String, whenIso: String) =
        write(planId, PlanSentences.OFFER) { planRepository.offerHour(planId, whenIso) }

    /** Agree to the hour the other half named, sending back exactly the instant that was read. */
    fun confirmHour(planId: String, whenIso: String) =
        write(planId, PlanSentences.CONFIRM) { planRepository.confirmHour(planId, whenIso) }

    /**
     * Write the pair's place and their note about it, or take one of the two back.
     *
     * What leaves the device is read off the plan this page already holds, not off the fields alone:
     * text that matches the stored word sends nothing, a field the person emptied while the plan still
     * named it is sent as its own erasure, and a tap that moved neither of the two is dropped rather
     * than paid for with a request that could only answer «ничего не изменилось».
     */
    fun saveWords(planId: String, placeText: String, noteText: String) {
        val plan = _uiState.value.plans.firstOrNull { it.id == planId } ?: return
        val edit = planWordsEdit(plan, placeText, noteText)
        if (edit.nothingChanged) return
        write(planId, PlanSentences.WORDS) {
            planRepository.editWords(planId, edit.place, edit.note, edit.clearPlace, edit.clearNote)
        }
    }

    fun cancel(planId: String) = write(planId, PlanSentences.CANCEL) { planRepository.cancel(planId) }

    fun restore(planId: String) = write(planId, PlanSentences.RESTORE) { planRepository.restore(planId) }

    /** This person's own word that the meeting happened; the plan says «состоялось» only for two. */
    fun markAttended(planId: String) =
        write(planId, PlanSentences.ATTEND) { planRepository.markAttended(planId) }

    fun undoAttended(planId: String) =
        write(planId, PlanSentences.UNDO_ATTEND) { planRepository.undoAttended(planId) }

    /**
     * One tap, one request, then the page read back.
     *
     * The reload is not a courtesy: these verbs move facts the other half owns too — an hour the pair
     * stands on, a refusal that answers an idea — and the screen that kept its own answer of the pair
     * would be a second copy of a plan the server has already moved. A write that came back refused
     * skips the read: nothing changed, so the card stays exactly where the tap can be made again.
     */
    private fun write(planId: String, sentence: String, call: suspend () -> ApiResult<Unit>) {
        if (_uiState.value.busy.contains(planId)) return
        _uiState.update { it.copy(busy = it.busy + planId, tapErrors = it.tapErrors - planId) }
        viewModelScope.launch {
            when (val result = call()) {
                is ApiResult.Error -> _uiState.update {
                    it.copy(
                        busy = it.busy - planId,
                        tapErrors = it.tapErrors + (planId to reasonSentence(sentence, result.message)),
                    )
                }
                is ApiResult.Success -> {
                    _uiState.update { it.copy(busy = it.busy - planId) }
                    load()
                }
            }
        }
    }
}
