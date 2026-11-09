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

enum class RootDestination {
    LOADING,
    AUTH,
    /** The text on file is no longer the one the product publishes; read and accept the current one. */
    CONSENT,
    /** The account exists but the letter sent to its address was never answered. */
    EMAIL_CONFIRMATION,
    ONBOARDING,
    MAIN,
}

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
                // Two account-level gates precede the profile one, in the order a person can act on
                // them. Consent first: an account that never named the text it accepted has no basis
                // on record, and re-accepting is one screen with no mailbox involved. The address
                // next: an unconfirmed account is invisible to everybody else's deck on the server
                // (`social_repo._candidate_conditions`), so sending it to onboarding would ask it to
                // fill a profile nobody can be shown and then announce «Анкеты закончились» as if
                // that were the product rather than the letter.
                when {
                    !profile.consentUpToDate -> RootDestination.CONSENT
                    !profile.emailVerified -> RootDestination.EMAIL_CONFIRMATION
                    // The server's own stamp, not a guess from the fields: registration leaves a shell
                    // already holding a name and a goal, and a person who named no interests is a
                    // person who finished onboarding. Both read as «unfinished» to any field rule,
                    // and the second one loses their pair over it.
                    profile.onboardingCompleted -> RootDestination.MAIN
                    else -> RootDestination.ONBOARDING
                }
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
