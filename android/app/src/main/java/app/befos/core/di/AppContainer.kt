package app.befos.core.di

import android.content.Context
import app.befos.core.network.TokenStore
import app.befos.core.network.createHttpClient
import app.befos.data.remote.ApiService
import app.befos.data.repository.AuthRepositoryImpl
import app.befos.data.repository.ChatRepositoryImpl
import app.befos.data.repository.DiscoveryRepositoryImpl
import app.befos.data.repository.MatchRepositoryImpl
import app.befos.data.repository.ModerationRepositoryImpl
import app.befos.data.repository.PlanRepositoryImpl
import app.befos.data.repository.ProfileRepositoryImpl
import app.befos.data.repository.ReferralRepositoryImpl
import app.befos.data.repository.SafetyRepositoryImpl
import app.befos.data.repository.TestRepositoryImpl
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.repository.MatchRepository
import app.befos.domain.repository.ModerationRepository
import app.befos.domain.repository.PlanRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.ReferralRepository
import app.befos.domain.repository.SafetyRepository
import app.befos.domain.repository.TestRepository
import app.befos.domain.safety.AnsweredUsers
import io.ktor.client.HttpClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow

class AppContainer(context: Context) {
    val appScope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val tokenStore: TokenStore = TokenStore(context.applicationContext)

    // One instance for the whole process: the deck needs to hear that a person was answered
    // on the profile screen, which is a different route with a different ViewModel.
    val answeredUsers: AnsweredUsers = AnsweredUsers()

    // Building the HTTP stack costs well over a second (engine discovery, TLS
    // providers, coroutine dispatchers). Nothing is requested before the splash
    // frame, so keep it off Application.onCreate and pay it on first use.
    val httpClient: HttpClient by lazy { createHttpClient(tokenStore) }
    private val api: ApiService by lazy { ApiService(httpClient) }

    val authRepository: AuthRepository by lazy { AuthRepositoryImpl(api, tokenStore) }
    val profileRepository: ProfileRepository by lazy { ProfileRepositoryImpl(api) }
    val testRepository: TestRepository by lazy { TestRepositoryImpl(api) }
    val discoveryRepository: DiscoveryRepository by lazy { DiscoveryRepositoryImpl(api) }
    val referralRepository: ReferralRepository by lazy { ReferralRepositoryImpl(api) }

    /**
     * The invitation a deep link carried, until the registration form answers for it.
     *
     * It lives in process memory and not in storage on purpose: the link is opened to be spent by
     * *this* visit, and a code that outlived the visit would silently attach an unrelated future
     * account to a friend's name weeks later. The auth screen reads it, previews it without naming
     * anybody, and sends it with the registration; a success or an explicit «without an
     * invitation» clears it. The server still decides whether the code is live, spent or expired —
     * the client keeps the bearer secret, never the verdict about a person.
     */
    val registrationInviteCode = MutableStateFlow<String?>(null)

    fun openInvite(code: String?) {
        val cleaned = code?.trim().orEmpty()
        if (cleaned.isNotEmpty()) registrationInviteCode.value = cleaned
    }

    fun clearRegistrationInvite() {
        registrationInviteCode.value = null
    }

    val matchRepository: MatchRepository by lazy { MatchRepositoryImpl(api) }
    val planRepository: PlanRepository by lazy { PlanRepositoryImpl(api) }
    val safetyRepository: SafetyRepository by lazy { SafetyRepositoryImpl(api) }
    val moderationRepository: ModerationRepository by lazy { ModerationRepositoryImpl(api) }
    val chatRepository: ChatRepository by lazy {
        ChatRepositoryImpl(api, httpClient, tokenStore, appScope)
    }
}
