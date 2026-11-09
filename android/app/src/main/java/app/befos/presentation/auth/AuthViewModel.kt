package app.befos.presentation.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.ConsentDocument
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
    /**
     * The text the server publishes today, loaded when the register branch is first shown. Null
     * while it is on its way, and after a failed read — the error beside it says which of the two
     * the screen is looking at, and the register door does not open without it.
     */
    val consent: ConsentDocument? = null,
    val consentChecked: Boolean = false,
    val consentLoading: Boolean = false,
    val consentError: String? = null,
    val loading: Boolean = false,
    val error: String? = null,
    val success: Boolean = false,
)

class AuthViewModel(private val authRepository: AuthRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(AuthUiState())
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    init {
        // A device that never signed in should open on registration, not "welcome back".
        viewModelScope.launch {
            val remembered = authRepository.lastEmail()
            _uiState.update { s ->
                when {
                    s.email.isNotBlank() -> s
                    remembered == null -> s.copy(isRegister = true)
                    else -> s.copy(email = remembered)
                }
            }
            loadConsent()
        }
    }

    fun onEmailChange(v: String) = _uiState.update { it.copy(email = v, error = null) }
    fun onPasswordChange(v: String) = _uiState.update { it.copy(password = v, error = null) }
    fun onPasswordConfirmChange(v: String) = _uiState.update { it.copy(passwordConfirm = v, error = null) }

    fun onConsentChecked(v: Boolean) = _uiState.update {
        it.copy(consentChecked = v, error = null)
    }

    fun toggleMode() {
        _uiState.update {
            it.copy(
                isRegister = !it.isRegister,
                error = null,
                passwordConfirm = "",
                consentChecked = false,
            )
        }
        // Opening the register branch for the first time is the moment the text is needed. The read
        // is a no-op on the branches that already hold it, so a person flipping modes twice does not
        // ask the server twice.
        if (_uiState.value.isRegister) loadConsent()
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
        if (s.isRegister) {
            val document = s.consent
            if (document == null) {
                _uiState.update {
                    it.copy(
                        error = s.consentError
                            ?: "Текст согласия ещё не загрузился. Проверьте связь и попробуйте ещё раз.",
                    )
                }
                loadConsent()
                return
            }
            if (!s.consentChecked) {
                _uiState.update { it.copy(error = "Прочитайте и примите текст согласия.") }
                return
            }
            register(email, s.password, document.version)
            return
        }
        login(email, s.password)
    }

    private fun register(email: String, password: String, consentVersion: String) {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = authRepository.register(email, password, consentVersion)) {
                is ApiResult.Success -> _uiState.update { it.copy(loading = false, success = true) }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    private fun login(email: String, password: String) {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            when (val result = authRepository.login(email, password)) {
                is ApiResult.Success -> _uiState.update { it.copy(loading = false, success = true) }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    private fun loadConsent() {
        val state = _uiState.value
        if (!state.isRegister || state.consent != null || state.consentLoading) return
        _uiState.update { it.copy(consentLoading = true, consentError = null) }
        viewModelScope.launch {
            when (val result = authRepository.consent()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(consent = result.data, consentLoading = false)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(consentLoading = false, consentError = result.message)
                }
            }
        }
    }

    private fun isValidEmail(email: String): Boolean =
        email.contains("@") && email.contains(".") && !email.startsWith("@") && !email.endsWith(".")
}
