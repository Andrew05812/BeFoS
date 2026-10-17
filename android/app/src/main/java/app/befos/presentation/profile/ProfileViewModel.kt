package app.befos.presentation.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.core.network.PHOTO_TYPES_SUPPORTED
import app.befos.core.network.PHOTO_UPLOAD_CONTENT_TYPES
import app.befos.domain.model.Profile
import app.befos.domain.model.TestProgress
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.TestRepository
import java.io.InputStream
import kotlinx.coroutines.CancellationException
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
    /** A picked picture is on its way to the server right now; the button holds still until it lands. */
    val uploading: Boolean = false,
    /** Why the last picture did not arrive, in the server's own Russian wording where it has one. */
    val uploadError: String? = null,
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

    /**
     * Send a picture the person chose to `POST /users/me/photo`, and paint the answer.
     *
     * The screen hands over the label the system put on the file and a way to open it, so this class
     * holds no `Uri` and no `ContentResolver`, and a refusal can be reasoned about without a device.
     * Two refusals are made here, before the uplink is paid for: a file the photo pipeline cannot
     * read is named as soon as it is named, and a file the system will not open is named too.
     * Everything else — the size, the canvas, a body that fails to decode — the server decides, and
     * its Russian answer is what lands in [ProfileUiState.uploadError].
     *
     * What appears on success is the picture list from the response, not the bytes that were sent:
     * the route re-encodes the file, stores it under a name it picked itself, and returns the whole
     * profile with the new photograph leading. A refusal therefore leaves the screen holding the
     * picture the server still has, which is the honest state of that tab.
     */
    fun uploadPhoto(contentType: String?, open: () -> InputStream) {
        if (_uiState.value.uploading) return
        if (contentType == null || contentType !in PHOTO_UPLOAD_CONTENT_TYPES) {
            _uiState.update { it.copy(uploadError = PHOTO_TYPES_SUPPORTED) }
            return
        }
        _uiState.update { it.copy(uploading = true, uploadError = null) }
        viewModelScope.launch {
            val result = try {
                profileRepository.uploadPhoto(open(), contentType)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                // Whatever it was — a provider that would not open, a file that stopped existing
                // mid-read — the picture never left the device, and the server has nothing to say
                // about it. Every failure the server *does* answer arrives as an ApiResult.Error.
                ApiResult.Error(-1, PHOTO_UNREADABLE)
            }
            when (result) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(uploading = false, profile = result.data, uploadError = null)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(uploading = false, uploadError = result.message)
                }
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

/**
 * A picture the device would not hand over. Distinct from every server refusal, which reaches this
 * screen already translated by `localizeBackendError`: this one is about the file, not the photo.
 */
private const val PHOTO_UNREADABLE = "Не удалось прочитать выбранное фото. Выберите его ещё раз."
