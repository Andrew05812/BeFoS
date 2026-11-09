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
 * The state of getting back into an account whose word was lost.
 *
 * Two screens, one flat state object, and deliberately no `stage` machine: the person leaves this
 * flow to read mail and comes back to it, and a flag inside one screen would have to survive that.
 * `letterSent` is the most the product is allowed to claim about the first half — the request was
 * accepted — and `minutes` is read off the server's own answer rather than typed in here, because a
 * promise about how long a code lives is a fact the backend owns.
 */
data class PasswordResetUiState(
    val email: String = "",
    val minutes: Int = 0,
    val letterSent: Boolean = false,
    val code: String = "",
    val newPassword: String = "",
    val passwordConfirm: String = "",
    val busy: Boolean = false,
    val done: Boolean = false,
    val error: String? = null,
)

class PasswordResetViewModel(private val authRepository: AuthRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(PasswordResetUiState())
    val uiState: StateFlow<PasswordResetUiState> = _uiState.asStateFlow()

    fun onEmailChange(value: String) =
        _uiState.update { it.copy(email = value, error = null, letterSent = false) }

    fun onCodeChange(value: String) = _uiState.update { it.copy(code = value, error = null) }

    fun onNewPasswordChange(value: String) = _uiState.update { it.copy(newPassword = value, error = null) }

    fun onConfirmChange(value: String) = _uiState.update { it.copy(passwordConfirm = value, error = null) }

    /**
     * Ask for the letter.
     *
     * The address is asked about before the wire is touched, for the same reason the login form does
     * it: an empty field is not a question the server can answer honestly. A success switches the
     * screen to the code, and the sentence is the same whether or not the address holds an account —
     * which is the point of the door, not a limitation of this client.
     */
    fun requestLetter() {
        val s = _uiState.value
        if (s.busy) return
        if (!isValidEmail(s.email)) {
            _uiState.update { it.copy(error = "Проверьте адрес почты.") }
            return
        }
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = authRepository.requestPasswordReset(s.email)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        busy = false,
                        letterSent = true,
                        minutes = (result.data + 59) / 60,
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(busy = false, error = result.message)
                }
            }
        }
    }

    /**
     * Spend the code on a new word.
     *
     * The three questions the server asks — is there a code, is the word long enough, did it get
     * said twice the same way — are asked here first, in the same order and with the same sentences
     * registration uses, so a mistyped confirmation costs nobody a round trip. A refusal leaves the
     * draft exactly where it was: the code the server refused is still the code the letter carried,
     * and a person who retypes a word should not have to go find the mail again.
     */
    fun spendCode() {
        val s = _uiState.value
        if (s.busy) return
        if (s.code.isBlank()) {
            _uiState.update { it.copy(error = "Введите код из письма.") }
            return
        }
        if (s.newPassword.length < 8) {
            _uiState.update { it.copy(error = "Пароль должен быть не короче 8 символов.") }
            return
        }
        if (s.newPassword != s.passwordConfirm) {
            _uiState.update { it.copy(error = "Пароли не совпадают.") }
            return
        }
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = authRepository.confirmPasswordReset(s.code, s.newPassword, s.passwordConfirm)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(busy = false, done = true, code = "", newPassword = "", passwordConfirm = "")
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(busy = false, error = result.message)
                }
            }
        }
    }

    private companion object {
        // The same predicate `AuthViewModel` uses, kept here rather than imported from another
        // screen's private helper: two forms that disagree about what an address is would be a bug
        // in the door a locked-out person stands in front of.
        fun isValidEmail(value: String): Boolean =
            value.contains("@") && value.indexOf('@') > 0 && value.length - value.indexOf('@') > 4
    }
}
