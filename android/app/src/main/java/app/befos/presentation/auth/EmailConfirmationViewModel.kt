package app.befos.presentation.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.repository.AuthRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * The state of proving the mailbox an account was registered with.
 *
 * `done` is set only by the server's 204. Nothing here flips a local flag called «verified» and hopes:
 * the deck is built by the same server from the same row, so a screen that celebrated its own guess
 * would show a person cards their account cannot get and letters their address cannot receive.
 *
 * `resent` is the most the resend door can honestly claim — the request was accepted. The server sends
 * no second letter while one still works (the first is the one that changes the flag), and it says
 * nothing about a confirmed address, so the screen's sentence is about checking mail, not about a
 * letter leaving the building.
 */
data class EmailConfirmationUiState(
    val code: String = "",
    val busy: Boolean = false,
    val done: Boolean = false,
    val resent: Boolean = false,
    val error: String? = null,
)

class EmailConfirmationViewModel(private val authRepository: AuthRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(EmailConfirmationUiState())
    val uiState: StateFlow<EmailConfirmationUiState> = _uiState.asStateFlow()

    fun onCodeChange(value: String) =
        _uiState.update { it.copy(code = value, error = null, resent = false) }

    fun confirm() {
        val state = _uiState.value
        if (state.busy) return
        if (state.code.isBlank()) {
            _uiState.update { it.copy(error = "Введите код из письма.") }
            return
        }
        _uiState.update { it.copy(busy = true, error = null, resent = false) }
        viewModelScope.launch {
            when (val result = authRepository.confirmEmail(state.code.trim())) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(busy = false, done = true, code = "")
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(busy = false, error = result.message)
                }
            }
        }
    }

    fun resend() {
        val state = _uiState.value
        if (state.busy) return
        _uiState.update { it.copy(busy = true, error = null, resent = false) }
        viewModelScope.launch {
            when (val result = authRepository.resendEmailConfirmation()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(busy = false, resent = true)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(busy = false, error = result.message)
                }
            }
        }
    }
}
