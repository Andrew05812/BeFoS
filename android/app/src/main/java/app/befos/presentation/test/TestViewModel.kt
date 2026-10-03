package app.befos.presentation.test

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Question
import app.befos.domain.repository.TestRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class TestUiState(
    val loading: Boolean = true,
    val questions: List<Question> = emptyList(),
    val index: Int = 0,
    val answers: Map<Int, Int> = emptyMap(),
    val submitting: Boolean = false,
    val result: List<CategoryScore>? = null,
    val error: String? = null,
) {
    val current: Question? get() = questions.getOrNull(index)
    val progress: Float get() = if (questions.isEmpty()) 0f else (index + 1) / questions.size.toFloat()
}

class TestViewModel(private val testRepository: TestRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(TestUiState())
    val uiState: StateFlow<TestUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = testRepository.questions()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(loading = false, questions = result.data, index = 0)
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
        val isLast = _uiState.value.index >= _uiState.value.questions.lastIndex
        _uiState.update { it.copy(answers = answers) }
        if (isLast) {
            finish(answers)
        } else {
            _uiState.update { it.copy(index = it.index + 1) }
        }
    }

    fun back() = _uiState.update { if (it.index > 0) it.copy(index = it.index - 1) else it }

    private fun finish(answers: Map<Int, Int>) {
        _uiState.update { it.copy(submitting = true, error = null) }
        viewModelScope.launch {
            when (val submitted = testRepository.submitAnswers(answers)) {
                is ApiResult.Error -> {
                    _uiState.update { it.copy(submitting = false, error = submitted.message) }
                    return@launch
                }
                is ApiResult.Success -> Unit
            }
            when (val completed = testRepository.complete()) {
                is ApiResult.Success -> _uiState.update { it.copy(submitting = false, result = completed.data) }
                is ApiResult.Error -> _uiState.update { it.copy(submitting = false, error = completed.message) }
            }
        }
    }
}
