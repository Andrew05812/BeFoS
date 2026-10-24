package app.befos.presentation.plans

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Message
import app.befos.domain.model.PlanHistory
import app.befos.domain.repository.PlanRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The word the page shows when the person's own remark would not land. */
const val PLAN_NOTE_REFUSED_WORD = "Не удалось сохранить своё слово."

data class PlanHistoryUiState(
    val loading: Boolean = true,
    val events: List<Message> = emptyList(),
    // This person's own remark, as the server holds it. Null is the honest answer to «nothing was
    // written», and the page reads it only after a successful read, so it never has to guess whether
    // an absent word was erased or merely not loaded yet.
    val myNote: String? = null,
    val error: String? = null,
    val noteBusy: Boolean = false,
    val noteError: String? = null,
)

/**
 * The story of one plan, read once and read again only when the person asks.
 *
 * The page is opened from a card the list already holds, and the server answers the plan with its own
 * journal lines and the reader's private remark attached, so one read carries all three — which is
 * why this screen holds no socket of its own: the pair's plans page is already listening to the
 * thread, and a second listener would make the person read one change twice. What the view model is
 * still answerable for is the four endings a read has: nothing read yet, a chronology, a refusal with
 * no rows behind it, and a refusal over the rows this device did manage to read.
 *
 * The write of a private word reloads quietly. A person who has just typed a sentence does not want
 * the page to blink back to a skeleton to prove the sentence was kept, and the rows the read carries
 * are the same rows already on screen — so only the remark has to catch up with the server, and if
 * that catch-up is refused the rows stay and are named as the last thing this device read.
 */
class PlanHistoryViewModel(
    private val planRepository: PlanRepository,
    private val planId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PlanHistoryUiState())
    val uiState: StateFlow<PlanHistoryUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch { read() }
    }

    /** Write, replace, or take back this person's own word about their own plan. */
    fun saveNote(typed: String) {
        if (_uiState.value.noteBusy) return
        val edit = planNoteEdit(_uiState.value.myNote, typed)
        if (edit.nothingChanged) return
        if (planNoteOverfall(typed) != null) return
        _uiState.update { it.copy(noteBusy = true, noteError = null) }
        viewModelScope.launch {
            when (val result = planRepository.saveNote(planId, edit.note)) {
                is ApiResult.Error -> _uiState.update {
                    val reason = result.message
                    it.copy(
                        noteBusy = false,
                        noteError = if (reason.isNullOrBlank()) PLAN_NOTE_REFUSED_WORD
                        else "$PLAN_NOTE_REFUSED_WORD $reason",
                    )
                }
                is ApiResult.Success -> {
                    _uiState.update { state -> state.copy(noteBusy = false) }
                    refresh()
                }
            }
        }
    }

    private suspend fun read(): PlanHistory? = when (val result = planRepository.history(planId)) {
        is ApiResult.Success -> {
            _uiState.update {
                it.copy(
                    loading = false,
                    events = result.data.lines,
                    myNote = result.data.myNote,
                    error = null,
                )
            }
            result.data
        }
        is ApiResult.Error -> {
            _uiState.update { it.copy(loading = false, error = result.message) }
            null
        }
    }

    /** The read a save asks for: the same rows, the server's own word on them, no skeleton between. */
    private fun refresh() {
        viewModelScope.launch {
            when (val result = planRepository.history(planId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        events = result.data.lines,
                        myNote = result.data.myNote,
                        error = null,
                    )
                }
                is ApiResult.Error -> _uiState.update { it.copy(error = result.message) }
            }
        }
    }
}
