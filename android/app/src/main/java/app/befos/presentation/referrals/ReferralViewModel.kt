package app.befos.presentation.referrals

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.Invite
import app.befos.domain.repository.ReferralRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ReferralsUiState(
    val loading: Boolean = true,
    val invites: List<Invite> = emptyList(),
    val acceptedTotal: Int = 0,
    val busy: Boolean = false,
    val error: String? = null,
    val notice: String? = null,
    /** The invitation whose «Отозвать» was tapped, waiting for the second tap. */
    val confirmRevokeId: String? = null,
) {
    val active: Invite? get() = invites.firstOrNull { it.isActive }
    val history: List<Invite> get() = invites.filterNot { it.isActive }
}

/**
 * The account's own door and what became of it.
 *
 * The screen never invents a status: every read replaces the list with the server's rows, because a
 * link's life (active, spent, revoked, expired) is decided by clocks and by other people, and a card
 * that kept saying «действует» after somebody used it would be the product lying about a fact it
 * can see. The same is why a create reloads instead of appending: the server may have handed back the
 * door that was already open.
 */
class ReferralViewModel(private val referralRepository: ReferralRepository) : ViewModel() {

    private val _uiState = MutableStateFlow(ReferralsUiState())
    val uiState: StateFlow<ReferralsUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = it.invites.isEmpty(), error = null) }
        viewModelScope.launch {
            when (val result = referralRepository.invites()) {
                is ApiResult.Success -> _uiState.update {
                    it.copy(
                        loading = false,
                        invites = result.data.invites,
                        acceptedTotal = result.data.acceptedTotal,
                        error = null,
                    )
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(loading = false, error = result.message)
                }
            }
        }
    }

    fun createInvite() {
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = referralRepository.createInvite()) {
                is ApiResult.Success -> {
                    _uiState.update { state ->
                        val withoutIt = state.invites.filterNot { it.id == result.data.id }
                        state.copy(
                            busy = false,
                            invites = listOf(result.data) + withoutIt,
                            notice = "Ссылка готова — её можно передать одному человеку.",
                            error = null,
                        )
                    }
                    load()
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(busy = false, error = result.message)
                }
            }
        }
    }

    fun askRevoke(invitationId: String) =
        _uiState.update { it.copy(confirmRevokeId = invitationId) }

    fun cancelRevoke() = _uiState.update { it.copy(confirmRevokeId = null) }

    fun revoke() {
        val invitationId = _uiState.value.confirmRevokeId ?: return
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = referralRepository.revokeInvite(invitationId)) {
                is ApiResult.Success -> {
                    _uiState.update {
                        it.copy(
                            busy = false,
                            confirmRevokeId = null,
                            notice = "Ссылка отозвана — открыть её больше нельзя.",
                        )
                    }
                    load()
                }
                is ApiResult.Error -> _uiState.update {
                    it.copy(busy = false, confirmRevokeId = null, error = result.message)
                }
            }
        }
    }

    fun clearNotice() = _uiState.update { it.copy(notice = null) }

    /** The words a share sheet carries: the link and what it is for, and no name of anybody. */
    fun shareText(invite: Invite): String =
        "Я в BeFoS — знакомства по совместимости. Вот моя личная ссылка: ${invite.url}"
}
