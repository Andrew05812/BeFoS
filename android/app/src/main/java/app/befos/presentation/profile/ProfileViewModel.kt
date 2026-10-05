package app.befos.presentation.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Profile
import app.befos.domain.model.TestProgress
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.TestRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ProfileUiState(
    val loading: Boolean = true,
    val profile: Profile? = null,
    val testProgress: TestProgress? = null,
    val testProgressFailed: Boolean = false,
    val error: String? = null,
    /**
     * A background refresh did not land, so what is on screen may be out of date. Separate
     * from [error], which replaces the screen.
     */
    val refreshError: String? = null,
    val signingOut: Boolean = false,
    val loggedOut: Boolean = false,
)

class ProfileViewModel(
    private val profileRepository: ProfileRepository,
    private val testRepository: TestRepository,
    private val authRepository: AuthRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ProfileUiState())
    val uiState: StateFlow<ProfileUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null, refreshError = null) }
        viewModelScope.launch {
            when (val result = profileRepository.me()) {
                is ApiResult.Success -> _uiState.update { it.copy(loading = false, profile = result.data) }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
            when (val progress = testRepository.progress()) {
                is ApiResult.Success -> _uiState.update { it.copy(testProgress = progress.data, testProgressFailed = false) }
                is ApiResult.Error -> _uiState.update { it.copy(testProgressFailed = true) }
            }
        }
    }

    /** Re-fetch after returning from edit-profile; keeps current content on screen. */
    fun refreshSilently() {
        if (_uiState.value.loading) return
        viewModelScope.launch {
            val me = profileRepository.me()
            val progress = testRepository.progress()
            _uiState.update { state ->
                var next = state.copy(refreshError = null)
                when (me) {
                    is ApiResult.Success -> next = next.copy(profile = me.data, error = null)
                    is ApiResult.Error -> next = if (next.profile == null) {
                        // Nothing cached: the failure is the screen, not a note about it.
                        next.copy(error = me.message)
                    } else {
                        next.copy(refreshError = me.message)
                    }
                }
                when (progress) {
                    is ApiResult.Success -> next = next.copy(
                        testProgress = progress.data,
                        testProgressFailed = false,
                    )
                    is ApiResult.Error -> next = if (next.testProgress == null) {
                        // The card already has a "did not load" state for a first failure.
                        next.copy(testProgressFailed = true)
                    } else {
                        // The percent stays on screen, so the screen has to say it may be old.
                        next.copy(refreshError = next.refreshError ?: progress.message)
                    }
                }
                next
            }
        }
    }

    fun logout() {
        // signingOut flips before the suspend call, so a double tap cannot sign out twice.
        if (_uiState.value.signingOut) return
        _uiState.update { it.copy(signingOut = true) }
        viewModelScope.launch {
            authRepository.logout()
            _uiState.update { it.copy(signingOut = false, loggedOut = true) }
        }
    }
}
