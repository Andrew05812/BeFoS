package app.befos.presentation.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.BlockedUser
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.SafetyRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class SettingsUiState(
    val hidden: Boolean = false,
    /**
     * Whether this account holds the moderator role, as the server's answer about itself said.
     *
     * The flag only chooses whether the entry to the queue is drawn. A read that never answered
     * leaves it false, which hides a door rather than opening one onto a refusal: the entry is the
     * convenience, and `GET /reports` is the permission.
     */
    val isModerator: Boolean = false,
    /**
     * The server never answered which way visibility is, so the switch shows the local
     * default rather than the account's real state. A privacy setting drawn from a guess has
     * to say so: the user cannot tell an off switch from a hidden profile.
     */
    val visibilityUnknown: Boolean = false,
    val busy: Boolean = false,
    val message: String? = null,
    val messageIsError: Boolean = false,
    val loggedOut: Boolean = false,
    val deleted: Boolean = false,
    val confirmDelete: Boolean = false,
    /**
     * The people this account holds behind a block, newest first, as the server listed them.
     *
     * Empty is a real answer here and must not be drawn as one the screen is sure of while the read
     * is still out — see [blocksLoaded].
     */
    val blocked: List<BlockedUser> = emptyList(),
    val blocksLoaded: Boolean = false,
    /** The read never answered, so the section cannot say either way whom the account hides. */
    val blocksUnknown: Boolean = false,
    val blocksBusy: Boolean = false,
    val confirmUnblock: BlockedUser? = null,
    /**
     * The account's own word, being replaced.
     *
     * Three fields rather than one dialog over the profile: the server asks the old word before it
     * writes the new one, and the new one has to be said twice before it is accepted — the same two
     * questions registration asks, in the same order.
     */
    val passwordEditorOpen: Boolean = false,
    val passwordOld: String = "",
    val passwordNew: String = "",
    val passwordConfirm: String = "",
)

class SettingsViewModel(
    private val safetyRepository: SafetyRepository,
    private val authRepository: AuthRepository,
    private val profileRepository: ProfileRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(SettingsUiState())
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    /** Sync the visibility switch and the blocked list with the server state on open. */
    fun load() {
        viewModelScope.launch {
            when (val result = profileRepository.me()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        hidden = result.data.isHidden,
                        // The same answer says which queue this account may open, so the door is drawn
                        // from what the server said rather than from a name the operator mentioned.
                        isModerator = result.data.isModerator,
                        visibilityUnknown = false,
                    )
                }
                is ApiResult.Error -> _uiState.update { it.copy(visibilityUnknown = true) }
            }
        }
        loadBlocks()
    }

    /**
     * Reads the account's own block list. The screen's «Повторить» on this section calls it
     * directly rather than [load], so retrying a list that failed does not re-read the profile too.
     *
     * Kept apart from the visibility read on purpose: the two answers gate different parts of the
     * screen, and a profile request that came back while this one did not must not put the section
     * into the «we could not check» state it is holding.
     */
    fun loadBlocks() {
        if (_uiState.value.blocksBusy) return
        _uiState.update { it.copy(blocksBusy = true) }
        viewModelScope.launch {
            when (val result = safetyRepository.blockedUsers()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(blocksBusy = false, blocked = result.data, blocksLoaded = true, blocksUnknown = false)
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(blocksBusy = false, blocksLoaded = false, blocksUnknown = true)
                }
            }
        }
    }

    fun setHidden(hidden: Boolean) {
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            when (val result = safetyRepository.setVisibility(hidden)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        busy = false,
                        hidden = hidden,
                        // The server just told us which way it is, so the switch is no longer a guess.
                        visibilityUnknown = false,
                        messageIsError = false,
                        message = if (hidden) "Вы скрыты из подбора." else "Вы снова видны в подборе.",
                    )
                }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, messageIsError = true, message = result.message) }
            }
        }
    }

    fun logout() {
        // busy is set before the suspend call, so a second tap in the same frame is a no-op.
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true) }
        viewModelScope.launch {
            authRepository.logout()
            _uiState.update { it.copy(busy = false, loggedOut = true) }
        }
    }

    fun askDelete() = _uiState.update { it.copy(confirmDelete = true) }
    fun cancelDelete() = _uiState.update { it.copy(confirmDelete = false) }

    fun askPasswordChange() = _uiState.update {
        it.copy(passwordEditorOpen = true, message = null, messageIsError = false)
    }

    /**
     * Closes the editor and drops the three words with it.
     *
     * A half-typed password left in the state is a secret the screen keeps showing after the person
     * has walked away from it, and it would be carried into the next attempt they open.
     */
    fun cancelPasswordChange() = _uiState.update {
        it.copy(passwordEditorOpen = false, passwordOld = "", passwordNew = "", passwordConfirm = "")
    }

    fun onPasswordOldChange(value: String) = _uiState.update { it.copy(passwordOld = value) }
    fun onPasswordNewChange(value: String) = _uiState.update { it.copy(passwordNew = value) }
    fun onPasswordConfirmChange(value: String) = _uiState.update { it.copy(passwordConfirm = value) }

    /**
     * Writes the new word, and signs this device out when the server accepts it.
     *
     * The two questions the server asks are asked here first, in the same order and with the same
     * words registration uses, so a person who mistypes does not spend a round trip to learn the
     * rule. A refusal leaves both words and the session exactly where they were: the account is not
     * half-changed by an attempt the server did not accept.
     */
    fun submitPasswordChange() {
        if (_uiState.value.busy) return
        val s = _uiState.value
        if (s.passwordOld.isEmpty()) {
            _uiState.update { it.copy(messageIsError = true, message = "Введите текущий пароль.") }
            return
        }
        if (s.passwordNew.length < 8) {
            _uiState.update { it.copy(messageIsError = true, message = "Пароль должен быть не короче 8 символов.") }
            return
        }
        if (s.passwordNew != s.passwordConfirm) {
            _uiState.update { it.copy(messageIsError = true, message = "Пароли не совпадают.") }
            return
        }
        _uiState.update { it.copy(busy = true, message = null) }
        viewModelScope.launch {
            when (val result = authRepository.changePassword(s.passwordOld, s.passwordNew, s.passwordConfirm)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        busy = false,
                        passwordEditorOpen = false,
                        passwordOld = "",
                        passwordNew = "",
                        passwordConfirm = "",
                        messageIsError = false,
                        // The account's other devices are signed out by the same write, and this one
                        // is among them: the screen goes to the login door, so the sentence is for
                        // whoever comes back with the email still in the field.
                        message = "Пароль изменён. Все устройства просят войти заново.",
                        loggedOut = true,
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(busy = false, messageIsError = true, message = result.message)
                }
            }
        }
    }

    fun deleteAccount() {
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true, confirmDelete = false) }
        viewModelScope.launch {
            when (val result = safetyRepository.deleteAccount()) {
                is ApiResult.Success -> {
                    authRepository.logout()
                    _uiState.update { it.copy(busy = false, deleted = true) }
                }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, messageIsError = true, message = result.message) }
            }
        }
    }

    /**
     * Arms the dialog for one person. A write is already out, so the tap is dropped rather than
     * arming a second dialog: [confirmUnblock] would return on its own guard and leave that dialog
     * open over a list that is about to be replaced by the server's answer.
     */
    fun askUnblock(user: BlockedUser) {
        if (_uiState.value.blocksBusy) return
        _uiState.update { it.copy(confirmUnblock = user) }
    }

    fun cancelUnblock() = _uiState.update { it.copy(confirmUnblock = null) }

    /**
     * Takes one block back and paints the list the server answered with.
     *
     * The row is dropped from the screen by that answer rather than by the local list minus the tap:
     * the write and the read are the same question, and a row the server still holds has to stay
     * visible with a working tap. A refusal — a block somebody else already removed, an account that
     * has gone — leaves the list exactly as it stood and says what the server said.
     */
    fun confirmUnblock() {
        val user = _uiState.value.confirmUnblock ?: return
        if (_uiState.value.blocksBusy) return
        _uiState.update { it.copy(confirmUnblock = null, blocksBusy = true) }
        viewModelScope.launch {
            when (val result = safetyRepository.unblock(user.userId)) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        blocksBusy = false,
                        blocked = result.data,
                        blocksLoaded = true,
                        blocksUnknown = false,
                        messageIsError = false,
                        message = "Вы разблокировали ${user.name}. Пара и переписка не вернутся.",
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(blocksBusy = false, blocksUnknown = false, messageIsError = true, message = result.message)
                }
            }
        }
    }

    fun clearMessage() = _uiState.update { it.copy(message = null) }
}
