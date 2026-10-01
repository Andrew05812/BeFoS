package app.befos.presentation.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.SafetyRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class SettingsUiState(
    val hidden: Boolean = false,
    val busy: Boolean = false,
    val message: String? = null,
    val loggedOut: Boolean = false,
    val deleted: Boolean = false,
    val confirmDelete: Boolean = false,
)

class SettingsViewModel(
    private val safetyRepository: SafetyRepository,
    private val authRepository: AuthRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(SettingsUiState())
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    fun setHidden(hidden: Boolean) {
        _uiState.update { it.copy(busy = true) }
        viewModelScope.launch {
            when (val result = safetyRepository.setVisibility(hidden)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(busy = false, hidden = hidden, message = if (hidden) "Вы скрыты из подбора." else "Вы снова видны в подборе.")
                }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, message = result.message) }
            }
        }
    }

    fun logout() {
        viewModelScope.launch {
            authRepository.logout()
            _uiState.update { it.copy(loggedOut = true) }
        }
    }

    fun askDelete() = _uiState.update { it.copy(confirmDelete = true) }
    fun cancelDelete() = _uiState.update { it.copy(confirmDelete = false) }

    fun deleteAccount() {
        _uiState.update { it.copy(busy = true, confirmDelete = false) }
        viewModelScope.launch {
            when (val result = safetyRepository.deleteAccount()) {
                is ApiResult.Success -> {
                    authRepository.logout()
                    _uiState.update { it.copy(busy = false, deleted = true) }
                }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, message = result.message) }
            }
        }
    }

    fun clearMessage() = _uiState.update { it.copy(message = null) }
}
