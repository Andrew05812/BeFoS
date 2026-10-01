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

data class AuthUiState(
    val isRegister: Boolean = false,
    val email: String = "",
    val password: String = "",
    val passwordConfirm: String = "",
    val loading: Boolean = false,
    val error: String? = null,
    val success: Boolean = false,
)

class AuthViewModel(private val authRepository: AuthRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(AuthUiState())
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    fun onEmailChange(v: String) = _uiState.update { it.copy(email = v, error = null) }
    fun onPasswordChange(v: String) = _uiState.update { it.copy(password = v, error = null) }
    fun onPasswordConfirmChange(v: String) = _uiState.update { it.copy(passwordConfirm = v, error = null) }
    fun toggleMode() = _uiState.update {
        it.copy(isRegister = !it.isRegister, error = null, passwordConfirm = "")
    }

    fun submit() {
        val s = _uiState.value
        if (s.loading) return
        val email = s.email.trim()
        if (!isValidEmail(email)) {
            _uiState.update { it.copy(error = "Введите корректный email.") }
            return
        }
        if (s.password.length < 8) {
            _uiState.update { it.copy(error = "Пароль должен быть не короче 8 символов.") }
            return
        }
        if (s.isRegister && s.password != s.passwordConfirm) {
            _uiState.update { it.copy(error = "Пароли не совпадают.") }
            return
        }
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            val result = if (s.isRegister) {
                authRepository.register(email, s.password)
            } else {
                authRepository.login(email, s.password)
            }
            when (result) {
                is ApiResult.Success -> _uiState.update { it.copy(loading = false, success = true) }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    private fun isValidEmail(email: String): Boolean =
        email.contains("@") && email.contains(".") && !email.startsWith("@") && !email.endsWith(".")
}
