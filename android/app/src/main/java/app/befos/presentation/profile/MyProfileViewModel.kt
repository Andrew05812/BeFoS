package app.befos.presentation.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.TestProfile
import app.befos.domain.model.TestProgress
import app.befos.domain.repository.TestRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class MyProfileUiState(
    val loading: Boolean = true,
    // Null while nothing has arrived, empty once the server has said there is nothing to show.
    // The screen needs the difference: a profile that has never been read is a person who has not
    // answered yet, and a profile read as empty is one the engine has never scored.
    val profile: TestProfile? = null,
    val progress: TestProgress? = null,
    val error: String? = null,
    /** The gaps did not arrive, so the profile on screen cannot say which sections are still short. */
    val progressFailed: Boolean = false,
    /**
     * A background refresh did not land, so what is on screen may be out of date. Separate from
     * [error], which replaces the screen.
     */
    val refreshError: String? = null,
) {
    /** How much of the questionnaire this person has actually answered — only ever what the server counted. */
    val answered: Int get() = progress?.answered ?: 0
    val total: Int get() = progress?.total ?: 0

    /** The sections the server itself still counts short, in the catalogue's order. */
    val openSections: List<CategoryProgress>
        get() = progress?.categories?.filter { it.answered < it.total } ?: emptyList()
}

/**
 * The person's own compatibility profile, opened at any time.
 *
 * Two reads, and neither of them writes. The profile comes from `GET /tests/profile` — the bands
 * and the axis positions the engine already holds — and the coverage comes from
 * `GET /tests/progress`, which is the route that counts the sections and their gaps. Reusing the
 * second is what keeps this screen from becoming a third place that counts answered questions its
 * own way: the percent here and the percent on the profile tab come out of the same two reads the
 * rest of the app already pays for.
 */
class MyProfileViewModel(
    private val testRepository: TestRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(MyProfileUiState())
    val uiState: StateFlow<MyProfileUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null, refreshError = null) }
        viewModelScope.launch {
            when (val result = testRepository.profile()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(loading = false, profile = result.data, error = null)
                }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
            when (val progress = testRepository.progress()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(progress = progress.data, progressFailed = false)
                }
                is ApiResult.Error -> _uiState.update { it.copy(progressFailed = true) }
            }
        }
    }

    /**
     * Re-read after returning from the questionnaire, keeping what is on screen.
     *
     * The scenario this exists for: a person left the profile screen, answered two more cards, and
     * came back. The bands they were shown are then the averages of answers they no longer hold, and
     * a screen that only loads on first composition would keep printing them. Where a refresh fails
     * the previous numbers stay — with [MyProfileUiState.refreshError] saying they may be old,
     * because silently stale numbers on a screen whose subject is one's own measurements are worse
     * than a notice.
     */
    fun refreshSilently() {
        if (_uiState.value.loading) return
        viewModelScope.launch {
            val stored = testRepository.profile()
            val progress = testRepository.progress()
            _uiState.update { state ->
                var next = state.copy(refreshError = null)
                when (stored) {
                    is ApiResult.Success -> next = next.copy(profile = stored.data, error = null)
                    is ApiResult.Error -> next = if (next.profile == null) {
                        // Nothing cached: the failure is the screen, not a note about it.
                        next.copy(error = stored.message)
                    } else {
                        next.copy(refreshError = stored.message)
                    }
                }
                when (progress) {
                    is ApiResult.Success -> next = next.copy(progress = progress.data, progressFailed = false)
                    is ApiResult.Error -> next = if (next.progress == null) {
                        next.copy(progressFailed = true)
                    } else {
                        next.copy(refreshError = next.refreshError ?: progress.message)
                    }
                }
                next
            }
        }
    }
}
