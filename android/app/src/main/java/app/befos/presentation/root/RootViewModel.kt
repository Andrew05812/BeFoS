package app.befos.presentation.root

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.befos.core.network.ApiResult
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ProfileRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

enum class RootDestination { LOADING, AUTH, ONBOARDING, MAIN }

class RootViewModel(
    private val authRepository: AuthRepository,
    private val profileRepository: ProfileRepository,
) : ViewModel() {

    private val _destination = MutableStateFlow(RootDestination.LOADING)
    val destination: StateFlow<RootDestination> = _destination.asStateFlow()

    init {
        resolve()
    }

    fun resolve() {
        _destination.value = RootDestination.LOADING
        viewModelScope.launch {
            // A suspended backend answers the handshake but never replies, and the connect
            // timeout cannot catch that. Without a ceiling the launch splash holds forever
            // with no way out, so an unresolved gate falls through to MAIN, where the
            // screens own the failure and offer a retry.
            val destination = withTimeoutOrNull(GATE_TIMEOUT_MS) { route() } ?: RootDestination.MAIN
            _destination.value = destination
        }
    }

    private suspend fun route(): RootDestination {
        val auth = authRepository.current() ?: return RootDestination.AUTH
        return when (val result = profileRepository.me()) {
            is ApiResult.Success -> {
                val profile = result.data
                val onboarded = profile.name.isNotBlank() &&
                    profile.interests.isNotEmpty() &&
                    profile.datingGoal.isNotBlank()
                if (onboarded) RootDestination.MAIN else RootDestination.ONBOARDING
            }
            is ApiResult.Error -> {
                // The session is over only when the client itself gave up on it: a refresh
                // that the backend refused clears the stored tokens before this call
                // returns. A 401 with tokens still stored means the refresh could not
                // happen at all (outage, restart, network) — the session is intact, so this
                // goes to MAIN, where the screens own the retry, instead of erasing a
                // signed-in user over a hiccup.
                if (result.code == 401 && authRepository.current() == null) {
                    RootDestination.AUTH
                } else {
                    RootDestination.MAIN
                }
            }
        }
    }

    private companion object {
        const val GATE_TIMEOUT_MS = 10_000L
    }
}
