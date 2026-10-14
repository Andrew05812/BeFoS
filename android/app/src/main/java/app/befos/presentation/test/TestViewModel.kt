package app.befos.presentation.test

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Question
import app.befos.domain.repository.TestRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

// The tap is on screen at once, so a write that did not reach the catalogue leaves the person
// holding an answer the profile does not know about. The notice says which of the two it is,
// because «ошибка» alone would read as the tap having failed.
private const val NOT_SAVED =
    "Ответы не дошли до сервера. На экране они видны, но в профиль ещё не легли — " +
        "повторите запись, как только будет сеть."

data class TestUiState(
    val loading: Boolean = true,
    val questions: List<Question> = emptyList(),
    val categories: List<CategoryProgress> = emptyList(),
    val index: Int = 0,
    val answers: Map<Int, Int> = emptyMap(),
    // Taps the person has made that the catalogue has not confirmed yet. Kept apart from
    // `answers` because the screen shows both states differently: a tap is on screen at once,
    // and only the notice about an unconfirmed one tells the person their answer is not stored.
    val unsaved: Map<Int, Int> = emptyMap(),
    // How many answers the person came back with, so the screen can say it is continuing rather
    // than starting, and can say it without counting the marks the person cannot see.
    val storedOnArrival: Int = 0,
    // The band the person was sent in for, kept after the catalogue arrives so the screen can name
    // the reason it did not open on question one. Null when the test was opened on its own.
    val openedSection: String? = null,
    val submitting: Boolean = false,
    val result: List<CategoryScore>? = null,
    val error: String? = null,
    val saveError: String? = null,
) {
    val current: Question? get() = questions.getOrNull(index)
    val currentCategory: CategoryProgress?
        get() = current?.let { question -> categories.firstOrNull { it.key == question.category } }
    val openedCategory: CategoryProgress?
        get() = openedSection?.let { key -> categories.firstOrNull { it.key == key } }
    val progress: Float get() = if (questions.isEmpty()) 0f else (index + 1) / questions.size.toFloat()

    // Driven by the taps that are still waiting, not by the flag a failed write left behind: a
    // person who is holding an answer the catalogue does not have deserves to be told so, whether
    // or not this session has already seen the refusal.
    val pendingNotice: String? get() = if (unsaved.isEmpty()) null else (saveError ?: NOT_SAVED)
}

/**
 * Where the screen opens: the first card of [section] this person has not marked, so a band of the
 * compatibility screen sends them to the work that is actually left in that section rather than to
 * question one of a test they are halfway through.
 *
 * A section nobody has left unanswered opens on its first question — going back over one's own
 * answers is what «Назад» is for. A section the catalogue does not ask about at all (a band the
 * test does not measure) falls back to the whole-test rule instead of dead-ending on an empty list.
 */
internal fun startIndex(questions: List<Question>, section: String?): Int {
    if (section.isNullOrEmpty()) {
        return questions.indexOfFirst { it.selectedOptionId == null }.coerceAtLeast(0)
    }
    val ofSection = questions.withIndex().filter { (_, q) -> q.category == section }
    if (ofSection.isEmpty()) {
        return questions.indexOfFirst { it.selectedOptionId == null }.coerceAtLeast(0)
    }
    return ofSection.firstOrNull { (_, q) -> q.selectedOptionId == null }?.index
        ?: ofSection.first().index
}

class TestViewModel(
    private val testRepository: TestRepository,
    private val startSection: String? = null,
) : ViewModel() {

    private val _uiState = MutableStateFlow(TestUiState())
    val uiState: StateFlow<TestUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = testRepository.catalog()) {
                is ApiResult.Success -> {
                    val questions = result.data.questions
                    val stored = questions.mapNotNull { q -> q.selectedOptionId?.let { q.id to it } }.toMap()
                    // A test left halfway used to reopen on question one, so the person had to re-tap
                    // the questions they had answered to reach the one they had not — and a re-tap
                    // overwrites their own earlier answer. The first card the catalogue hands back
                    // unmarked is where they stopped.
                    val resumeAt = startIndex(questions, startSection)
                    _uiState.update {
                        it.copy(
                            loading = false,
                            questions = questions,
                            categories = result.data.categories,
                            answers = stored,
                            storedOnArrival = stored.size,
                            index = resumeAt,
                            openedSection = startSection,
                            unsaved = emptyMap(),
                            saveError = null,
                        )
                    }
                }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    fun select(optionId: Int) {
        if (_uiState.value.submitting) return
        val q = _uiState.value.current ?: return
        val answers = _uiState.value.answers.toMutableMap()
        answers[q.id] = optionId
        val unsaved = _uiState.value.unsaved.toMutableMap()
        unsaved[q.id] = optionId
        val isLast = _uiState.value.index >= _uiState.value.questions.lastIndex
        _uiState.update { it.copy(answers = answers, unsaved = unsaved) }
        if (isLast) {
            // `finish` posts the whole map, so the last tap is written by that request and its
            // confirmation clears the pending set with it.
            finish(answers)
        } else {
            _uiState.update { it.copy(index = it.index + 1) }
            record(q.id, optionId)
        }
    }

    fun back() = _uiState.update { if (it.index > 0) it.copy(index = it.index - 1) else it }

    /**
     * The thumb of a scale question came to rest on one of that question's own stops. Unlike
     * [select] this does not move the person on: a level is something one sets, passes and comes
     * back to, and a flow that turned every release into a page turn would be four taps wearing a
     * slider. The write is the same one a tap pays, so a released level is in the profile before
     * the person has asked to leave the question.
     */
    fun slide(optionId: Int) {
        if (_uiState.value.submitting) return
        val q = _uiState.value.current ?: return
        val answers = _uiState.value.answers.toMutableMap()
        answers[q.id] = optionId
        val unsaved = _uiState.value.unsaved.toMutableMap()
        unsaved[q.id] = optionId
        _uiState.update { it.copy(answers = answers, unsaved = unsaved) }
        record(q.id, optionId)
    }

    /**
     * «Далее» for a question the person sets with a thumb. Cards move on their own because a tap
     * cannot mean anything but an answer; a released thumb can still be a level about to be
     * changed, so moving on is asked for. Asked before any stop is held, it moves nothing and
     * writes nothing: there is no answer to carry forward, and inventing one would put words the
     * person never chose into their profile.
     */
    fun next() {
        val state = _uiState.value
        if (state.submitting) return
        val q = state.current ?: return
        if (state.answers[q.id] == null) return
        if (state.index >= state.questions.lastIndex) finish(state.answers)
        else _uiState.update { it.copy(index = it.index + 1) }
    }

    /** Re-posts what the catalogue has not confirmed, as one batch. */
    fun retryRecords() {
        val pending = _uiState.value.unsaved
        if (pending.isEmpty()) return
        viewModelScope.launch {
            when (testRepository.submitAnswers(pending)) {
                is ApiResult.Success -> _uiState.update { it.copy(unsaved = emptyMap(), saveError = null) }
                is ApiResult.Error -> _uiState.update { it.copy(saveError = NOT_SAVED) }
            }
        }
    }

    private fun record(questionId: Int, optionId: Int) {
        viewModelScope.launch {
            when (testRepository.submitAnswers(mapOf(questionId to optionId))) {
                is ApiResult.Success -> _uiState.update { state ->
                    // Only this tap leaves the pending set. A newer tap on the same question stays,
                    // because the server has now been told about an older choice of it.
                    val confirmed = state.unsaved[questionId] == optionId
                    state.copy(unsaved = if (confirmed) state.unsaved - questionId else state.unsaved)
                }
                is ApiResult.Error -> _uiState.update { it.copy(saveError = NOT_SAVED) }
            }
        }
    }

    private fun finish(answers: Map<Int, Int>) {
        _uiState.update { it.copy(submitting = true, error = null) }
        viewModelScope.launch {
            when (val submitted = testRepository.submitAnswers(answers)) {
                is ApiResult.Error -> {
                    _uiState.update { it.copy(submitting = false, error = submitted.message) }
                    return@launch
                }
                // The whole map went through, so nothing the person tapped is waiting anymore.
                is ApiResult.Success -> _uiState.update { it.copy(unsaved = emptyMap(), saveError = null) }
            }
            when (val completed = testRepository.complete()) {
                is ApiResult.Success -> _uiState.update { it.copy(submitting = false, result = completed.data) }
                is ApiResult.Error -> _uiState.update { it.copy(submitting = false, error = completed.message) }
            }
        }
    }
}
