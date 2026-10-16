package app.befos.presentation.plans

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Plan
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
}

private fun reasonSentence(sentence: String, reason: String?) =
    if (reason.isNullOrBlank()) sentence else "$sentence $reason"

data class PlansUiState(
    val loading: Boolean = true,
    val plans: List<Plan> = emptyList(),
    val error: String? = null,
    // Why the last tap on this plan did not land, one line per plan. A plan is a row the pair reads
    // as its own card, so a refusal says which card it refused rather than floating above the list.
    val tapErrors: Map<String, String> = emptyMap(),
    // Plans whose write has not been answered yet. A card that is busy takes no second tap: two
    // requests for the same verb would ask the pair to say the same thing twice.
    val busy: Set<String> = emptySet(),
)

class PlansViewModel(
    private val planRepository: PlanRepository,
    private val matchId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PlansUiState())
    val uiState: StateFlow<PlansUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = planRepository.plans(matchId)) {
                // The page is the pair's record, so it ends the doubt a refused write left: the card
                // repaints from what the server says rather than from what this visit tried to do.
                is ApiResult.Success -> _uiState.update {
                    it.copy(loading = false, plans = result.data, tapErrors = emptyMap())
                }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
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
