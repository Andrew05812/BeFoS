package app.befos.presentation.publicprofile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.LikeOutcome
import app.befos.domain.model.PublicProfile
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.SafetyRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PublicProfileUiState(
    val loading: Boolean = true,
    val profile: PublicProfile? = null,
    val error: String? = null,
    val busy: Boolean = false,
    val match: LikeOutcome? = null,
    val blocked: Boolean = false,
    val reportDialog: Boolean = false,
    val reportReason: String = "",
    val reportDetails: String = "",
    val notice: String? = null,
    val gone: Boolean = false,
)

class PublicProfileViewModel(
    private val profileRepository: ProfileRepository,
    private val discoveryRepository: DiscoveryRepository,
    private val safetyRepository: SafetyRepository,
    private val userId: String,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PublicProfileUiState())
    val uiState: StateFlow<PublicProfileUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = profileRepository.publicProfile(userId)) {
                is ApiResult.Success -> _uiState.update { it.copy(loading = false, profile = result.data) }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    fun like() {
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true) }
        viewModelScope.launch {
            when (val result = discoveryRepository.like(userId)) {
                is ApiResult.Success -> _uiState.update {
                    if (result.data.matched) it.copy(busy = false, match = result.data)
                    else it.copy(busy = false, notice = "Лайк отправлен", gone = true)
                }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, error = result.message) }
            }
        }
    }

    fun pass() {
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true) }
        viewModelScope.launch {
            when (val result = discoveryRepository.pass(userId)) {
                is ApiResult.Success -> _uiState.update { it.copy(busy = false, gone = true) }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, error = result.message) }
            }
        }
    }

    fun block() {
        _uiState.update { it.copy(busy = true) }
        viewModelScope.launch {
            when (val result = safetyRepository.block(userId)) {
                is ApiResult.Success -> _uiState.update { it.copy(busy = false, blocked = true, gone = true) }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, error = result.message) }
            }
        }
    }

    fun openReport() = _uiState.update { it.copy(reportDialog = true) }
    fun closeReport() = _uiState.update { it.copy(reportDialog = false) }
    fun onReportReason(v: String) = _uiState.update { it.copy(reportReason = v) }
    fun onReportDetails(v: String) = _uiState.update { it.copy(reportDetails = v) }

    fun submitReport() {
        val reason = _uiState.value.reportReason.trim()
        if (reason.length < 2) {
            _uiState.update { it.copy(notice = "Укажите причину (минимум 2 символа).") }
            return
        }
        viewModelScope.launch {
            when (val result = safetyRepository.report(userId, reason, _uiState.value.reportDetails.trim().ifBlank { null })) {
                is ApiResult.Success -> _uiState.update { it.copy(reportDialog = false, notice = "Жалоба отправлена", gone = true) }
                is ApiResult.Error -> _uiState.update { it.copy(notice = result.message) }
            }
        }
    }

    fun dismissMatch() = _uiState.update { it.copy(match = null, gone = true) }
}
