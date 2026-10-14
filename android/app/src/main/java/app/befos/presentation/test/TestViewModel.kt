package app.befos.presentation.test

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Question
import app.befos.domain.model.TestProgress
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
    // The band the person was sent in for, as the catalogue counted it at arrival. Kept as its own
    // numbers rather than read back out of `categories`, because the line explaining where the
    // screen opened is about the arrival: rewritten mid-walk it would become a second counter that
    // disagrees with the first by design. Null when the test was opened on its own.
    val openedBand: CategoryProgress? = null,
    // The sections a refused scoring attempt was short of, in the counts the server itself gave
    // back. Empty while the screen has nothing to send the person back into.
    val openSections: List<CategoryProgress> = emptyList(),
    val submitting: Boolean = false,
    val result: List<CategoryScore>? = null,
    val error: String? = null,
    val saveError: String? = null,
) {
    val current: Question? get() = questions.getOrNull(index)
    val currentCategory: CategoryProgress?
        get() = current?.let { question -> categories.firstOrNull { it.key == question.category } }
    val progress: Float get() = if (questions.isEmpty()) 0f else (index + 1) / questions.size.toFloat()

    /**
     * What the sections the server itself counted say about the questionnaire: every band it
     * reported holds an answer for all of its questions.
     *
     * The counts arrive only with writes that landed, and a band can never be counted above its own
     * questions, so a closed set of bands leaves no card empty — the route that refuses to score a
     * short questionnaire has nothing left to refuse. The position in the catalogue says nothing of
     * the sort: a person who was sent into one section walks it and stands in the middle of a test
     * they have in fact finished. Without counts the screen keeps its old rule (no band can be
     * named closed, so nothing is promised that the server has not confirmed).
     */
    val questionnaireClosed: Boolean
        get() = categories.isNotEmpty() && categories.all { it.answered >= it.total }

    /** What the forward press asks for: the profile, or the next card. */
    val finishesOnNext: Boolean get() = questionnaireClosed || index >= questions.lastIndex

    /** Whether the finishing button stands before the end of the catalogue, where its appearing needs saying. */
    val explainsEarlyFinish: Boolean get() = questionnaireClosed && index < questions.lastIndex

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

/**
 * The section counts the server just confirmed, in place of the ones the screen printed until now.
 *
 * Every write is answered with the counts of the whole questionnaire, so the line next to the
 * section label can move on the tap that landed instead of waiting for a reload. A response from
 * before the sections were reported carries none, and then the arrived counts stay — the line would
 * otherwise disappear under the person's own answers.
 *
 * The invitation to go back into a short section is re-read from the same counts, because it is a
 * reading of them and not a place the person was sent to: the section whose gap the last write
 * filled would otherwise keep its old numbers on screen next to the new ones, and an invitation
 * naming no gap left would keep offering a walk that has nothing to walk into.
 */
private fun TestUiState.withCounts(progress: TestProgress): TestUiState =
    if (progress.categories.isEmpty()) this
    else copy(
        categories = progress.categories,
        openSections = if (openSections.isEmpty()) emptyList()
        else progress.categories.filter { it.answered < it.total },
    )

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
                            openedBand = result.data.categories.firstOrNull { band -> band.key == startSection },
                            openSections = emptyList(),
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
     *
     * Once the counts say no section is short, the same press asks for the profile instead of the
     * next card. The person who came in through one section has filled the gap that sent them there
     * and is standing in the middle of the catalogue; making them page to its end to be scored would
     * charge a walk their own answers already finished.
     */
    fun next() {
        val state = _uiState.value
        if (state.submitting) return
        val q = state.current ?: return
        if (state.answers[q.id] == null) return
        if (state.finishesOnNext) finish(state.answers)
        else _uiState.update { it.copy(index = it.index + 1) }
    }

    /** Re-posts what the catalogue has not confirmed, as one batch. */
    fun retryRecords() {
        val pending = _uiState.value.unsaved
        if (pending.isEmpty()) return
        viewModelScope.launch {
            when (val written = testRepository.submitAnswers(pending)) {
                is ApiResult.Success -> _uiState.update { state ->
                    state.copy(unsaved = emptyMap(), saveError = null).withCounts(written.data)
                }
                is ApiResult.Error -> _uiState.update { it.copy(saveError = NOT_SAVED) }
            }
        }
    }

    private fun record(questionId: Int, optionId: Int) {
        viewModelScope.launch {
            when (val written = testRepository.submitAnswers(mapOf(questionId to optionId))) {
                is ApiResult.Success -> _uiState.update { state ->
                    // Only this tap leaves the pending set. A newer tap on the same question stays,
                    // because the server has now been told about an older choice of it.
                    val confirmed = state.unsaved[questionId] == optionId
                    state.copy(
                        unsaved = if (confirmed) state.unsaved - questionId else state.unsaved,
                        // The question is marked either way, so the section count the route returns
                        // is the person's own work either way — and it arrives with the write, so
                        // the line under the counter moves on the tap instead of on the next reload.
                    ).withCounts(written.data)
                }
                is ApiResult.Error -> _uiState.update { it.copy(saveError = NOT_SAVED) }
            }
        }
    }

    private fun finish(answers: Map<Int, Int>) {
        _uiState.update { it.copy(submitting = true, error = null, openSections = emptyList()) }
        viewModelScope.launch {
            when (val submitted = testRepository.submitAnswers(answers)) {
                is ApiResult.Error -> {
                    _uiState.update { it.copy(submitting = false, error = submitted.message) }
                    return@launch
                }
                // The whole map went through, so nothing the person tapped is waiting anymore, and
                // the counts this response carries are the ones the refusal below is read against.
                is ApiResult.Success -> _uiState.update { state ->
                    state.copy(unsaved = emptyMap(), saveError = null).withCounts(submitted.data)
                }
            }
            when (val completed = testRepository.complete()) {
                is ApiResult.Success -> _uiState.update { it.copy(submitting = false, result = completed.data) }
                is ApiResult.Error -> _uiState.update { state ->
                    // The route refuses to score a questionnaire it still counts short, and the
                    // sections it is short in are the ones the writes just named. Where they are,
                    // the person gets those numbers and a way into the section rather than a
                    // sentence to retry; where they are not, the refusal is the server's own reason
                    // and stays its own — an invitation built on counts that say «finished» would
                    // describe a failure the client cannot see.
                    val open = state.categories.filter { it.answered < it.total }
                    state.copy(
                        submitting = false,
                        openSections = open,
                        error = if (open.isEmpty()) completed.message else null,
                    )
                }
            }
        }
    }

    /**
     * The person took the invitation: the screen moves to the first card of the section the server
     * counted short, and the invitation goes away with the move — its numbers are the arrival's, and
     * leaving them on screen while the person answers a different section would keep a count of a
     * moment that has passed.
     */
    fun goToFirstOpenSection() {
        val band = _uiState.value.openSections.firstOrNull() ?: return
        _uiState.update {
            it.copy(
                index = startIndex(it.questions, band.key),
                openSections = emptyList(),
                error = null,
            )
        }
    }
}
