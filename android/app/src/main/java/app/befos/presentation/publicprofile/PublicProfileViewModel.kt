package app.befos.presentation.publicprofile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.model.LikeOutcome
import app.befos.domain.model.PublicProfile
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.repository.MatchRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.SafetyRepository
import app.befos.domain.safety.AnsweredUsers
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
    val blockDialog: Boolean = false,
    val reportDialog: Boolean = false,
    val reportReason: String = "",
    val reportDetails: String = "",
    val reportError: String? = null,
    val gone: Boolean = false,
    val partner: Boolean = false,
)

class PublicProfileViewModel(
    private val profileRepository: ProfileRepository,
    private val discoveryRepository: DiscoveryRepository,
    private val safetyRepository: SafetyRepository,
    private val answeredUsers: AnsweredUsers,
    private val matchRepository: MatchRepository,
    private val userId: String,
    private val matchId: String? = null,
) : ViewModel() {

    // Opened from a chat there is no user id to start from, and none is needed: `partner(matchId)`
    // answers the card of the person the pair is with. Every write below targets the id that arrived
    // with the card, because a card read by a pair knows a person the route never named.
    private var peerId: String = userId

    private val _uiState = MutableStateFlow(PublicProfileUiState(partner = matchId != null))
    val uiState: StateFlow<PublicProfileUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        _uiState.update { it.copy(loading = true, error = null) }
        viewModelScope.launch {
            // The deck route filters by «Скрыть из подбора» on purpose, and stage 113 pinned that
            // it stays so for a card id copied out of a link. A pair is not that reader: the route
            // it has proves membership, so the partner's card is asked there and answers even after
            // the partner stopped showing in the deck.
            val result = if (matchId != null) matchRepository.partner(matchId)
            else profileRepository.publicProfile(userId)
            when (result) {
                is ApiResult.Success -> {
                    peerId = result.data.userId
                    _uiState.update { it.copy(loading = false, profile = result.data) }
                }
                is ApiResult.Error -> _uiState.update { it.copy(loading = false, error = result.message) }
            }
        }
    }

    fun like() {
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.like(peerId)) {
                is ApiResult.Success -> {
                    answeredOnce()
                    _uiState.update {
                        if (result.data.matched) it.copy(busy = false, match = result.data) else it.copy(busy = false, gone = true)
                    }
                }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, error = result.message) }
            }
        }
    }

    fun pass() {
        if (_uiState.value.busy) return
        _uiState.update { it.copy(busy = true, error = null) }
        viewModelScope.launch {
            when (val result = discoveryRepository.pass(peerId)) {
                is ApiResult.Success -> {
                    answeredOnce()
                    _uiState.update { it.copy(busy = false, gone = true) }
                }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, error = result.message) }
            }
        }
    }

    fun askBlock() = _uiState.update { it.copy(blockDialog = true, error = null) }

    fun cancelBlock() = _uiState.update { it.copy(blockDialog = false) }

    /**
     * The block itself. It is reached only from the dialog, because the server deletes the
     * pair with its whole message history and the app has no way to undo any of that.
     */
    fun confirmBlock() {
        if (_uiState.value.busy) return
        _uiState.update { it.copy(blockDialog = false, busy = true, error = null) }
        viewModelScope.launch {
            when (val result = safetyRepository.block(peerId)) {
                is ApiResult.Success -> {
                    answeredOnce()
                    _uiState.update { it.copy(busy = false, gone = true) }
                }
                is ApiResult.Error -> _uiState.update { it.copy(busy = false, error = result.message) }
            }
        }
    }

    /**
     * Tells the deck this person is answered. The page of cards it holds in memory survives
     * this screen, so without the signal the same person — now blocked, or already liked —
     * is waiting as the next card.
     */
    private fun answeredOnce() = answeredUsers.publish(peerId)

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
                userId = peerId,
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
