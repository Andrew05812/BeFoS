package app.befos.presentation.publicprofile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.LikeOutcome
import app.befos.domain.model.PublicProfile
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.SafetyRepository
import app.befos.presentation.common.ReportReasonLabels
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
    val reportError: String? = null,
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
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.like(userId)) {
                is ApiResult.Success -> _uiState.update {
                    if (result.data.matched) it.copy(busy = false, match = result.data) else it.copy(busy = false, gone = true)
                }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, error = result.message) }
            }
        }
    }

    fun pass() {
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.pass(userId)) {
                is ApiResult.Success -> _uiState.update { it.copy(busy = false, gone = true) }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, error = result.message) }
            }
        }
    }

    fun block() {
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = safetyRepository.block(userId)) {
                is ApiResult.Success -> _uiState.update { it.copy(busy = false, blocked = true, gone = true) }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, error = result.message) }
            }
        }
    }

    fun openReport() = _uiState.update { it.copy(reportDialog = true, reportError = null) }
    fun closeReport() = _uiState.update { it.copy(reportDialog = false, reportError = null) }
    fun setReportReason(slug: String) = _uiState.update { it.copy(reportReason = slug, reportError = null) }
    fun onReportDetails(v: String) = _uiState.update { it.copy(reportDetails = v) }

    fun submitReport() {
        val s = _uiState.value
        if (s.busy) return
        if (!ReportReasonLabels.containsKey(s.reportReason)) {
            _uiState.update { it.copy(reportError = "Выберите причину из списка.") }
            return
        }
        _uiState.update { it.copy(busy = true, reportError = null) }
        viewModelScope.launch {
            val result = safetyRepository.report(
                userId = userId,
                reason = s.reportReason,
                details = s.reportDetails.trim().ifBlank { null },
            )
            when (result) {
                is ApiResult.Success -> _uiState.update { it.copy(busy = false, reportDialog = false, gone = true) }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, reportError = result.message) }
            }
        }
    }

    fun dismissMatch() = _uiState.update { it.copy(match = null, gone = true) }

    /**
     * Clears the match dialog for the "go to chat" path without flagging the screen as
     * finished — otherwise the back effect fires right after the chat push and pops it.
     */
    fun openChat() = _uiState.update { it.copy(match = null) }
}
