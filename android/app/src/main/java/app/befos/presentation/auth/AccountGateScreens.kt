package app.befos.presentation.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import app.befos.core.designsystem.AppButton
import app.befos.core.designsystem.AppTextField
import app.befos.core.designsystem.InlineNotice
import app.befos.core.designsystem.Spacing
import app.befos.core.di.beFosViewModel
import app.befos.domain.model.ConsentDocument
import app.befos.domain.repository.AuthRepository
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * The two doors a signed-in account can be stopped at before it reaches anything else.
 *
 * Both are shown by the start screen, not by a route inside the product, and both end with the same
 * move: the screen calls `rootVm.resolve()` and the server's own `/users/me` answer decides where the
 * person goes next. Neither screen keeps a local «passed» flag — the row is the only truth, so closing
 * the app in the middle of one of them cannot skip it.
 */
data class ConsentAcceptUiState(
    val document: ConsentDocument? = null,
    val checked: Boolean = false,
    val loading: Boolean = false,
    val busy: Boolean = false,
    val done: Boolean = false,
    val error: String? = null,
    val loadError: String? = null,
)

class ConsentAcceptViewModel(private val authRepository: AuthRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(ConsentAcceptUiState())
    val uiState: StateFlow<ConsentAcceptUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun onCheckedChange(value: Boolean) = _uiState.update { it.copy(checked = value, error = null) }

    fun accept() {
        val state = _uiState.value
        val document = state.document ?: return
        if (state.busy || !state.checked) return
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = authRepository.acceptConsent(document.version)) {
                is ApiResult.Success -> _uiState.update { it.copy(busy = false, done = true) }
                is ApiResult.Error -> _uiState.update {
                    it.copy(busy = false, error = result.message)
                }
            }
        }
    }

    private fun load() {
        if (_uiState.value.loading || _uiState.value.document != null) return
        _uiState.update { it.copy(loading = true, loadError = null) }
        viewModelScope.launch {
            when (val result = authRepository.consent()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(document = result.data, loading = false)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loading = false, loadError = result.message)
                }
            }
        }
    }
}

@Composable
fun EmailConfirmationScreen(onDone: () -> Unit) {
    val vm: EmailConfirmationViewModel = beFosViewModel { EmailConfirmationViewModel(it.authRepository) }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.done) { if (state.done) onDone() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .navigationBarsPadding()
            .padding(horizontal = Spacing.gutter, vertical = Spacing.xxl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        Text(
            text = "ПОДТВЕРДИТЕ АДРЕС",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = "Письмо уже в пути",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onBackground,
        )
        Text(
            text = "Мы отправили код на адрес, с которым вы зарегистрировались. Пока адрес не " +
                "подтверждён, анкета не показывается другим людям в подборе — всё, что вы успели " +
                "заполнить, остаётся на месте.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        AppTextField(
            value = state.code,
            onValueChange = vm::onCodeChange,
            label = "Код из письма",
            singleLine = true,
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Ascii,
                imeAction = ImeAction.Done,
            ),
            onImeAction = vm::confirm,
        )
        state.error?.let { InlineNotice(it) }
        if (state.resent) {
InlineNotice(
                text = "Проверьте почту и папку «Спам». Новое письмо уходит только после того, как " +
                    "срок предыдущего истёк.",
                isError = false,
            )
        }
        AppButton(
            text = "Подтвердить",
            onClick = vm::confirm,
            loading = state.busy,
            modifier = Modifier.fillMaxWidth(),
        )
        AppButton(
            text = "Письмо не пришло?",
            onClick = vm::resend,
            enabled = !state.busy,
            secondary = true,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
fun ConsentAcceptScreen(onDone: () -> Unit) {
    val vm: ConsentAcceptViewModel = beFosViewModel { ConsentAcceptViewModel(it.authRepository) }
    val state by vm.uiState.collectAsState()

    LaunchedEffect(state.done) { if (state.done) onDone() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .navigationBarsPadding()
            .padding(horizontal = Spacing.gutter, vertical = Spacing.xxl),
        verticalArrangement = Arrangement.spacedBy(Spacing.lg),
    ) {
        Text(
            text = "ОБНОВЛЕНИЕ СОГЛАСИЯ",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            text = "Текст согласия обновился",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.onBackground,
        )
        Text(
            text = "Мы изменили документ, который вы приняли при регистрации. Прочитайте новую " +
                "версию и примите её, чтобы продолжить пользоваться аккаунтом.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        ConsentPanel(
            document = state.document,
            checked = state.checked,
            onCheckedChange = vm::onCheckedChange,
            loading = state.loading,
            error = state.loadError,
        )
        state.error?.let { InlineNotice(it) }
        AppButton(
            text = "Принять и продолжить",
            onClick = vm::accept,
            enabled = state.document != null && state.checked && !state.loading,
            loading = state.busy,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}
