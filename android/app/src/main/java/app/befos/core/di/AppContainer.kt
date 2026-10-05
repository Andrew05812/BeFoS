package app.befos.core.di

import android.content.Context
import app.befos.core.network.TokenStore
import app.befos.core.network.createHttpClient
import app.befos.data.remote.ApiService
import app.befos.data.repository.AuthRepositoryImpl
import app.befos.data.repository.ChatRepositoryImpl
import app.befos.data.repository.DiscoveryRepositoryImpl
import app.befos.data.repository.MatchRepositoryImpl
import app.befos.data.repository.ProfileRepositoryImpl
import app.befos.data.repository.SafetyRepositoryImpl
import app.befos.data.repository.TestRepositoryImpl
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.repository.MatchRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.SafetyRepository
import app.befos.domain.repository.TestRepository
import app.befos.domain.safety.AnsweredUsers
import io.ktor.client.HttpClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

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
    val matchRepository: MatchRepository by lazy { MatchRepositoryImpl(api) }
    val safetyRepository: SafetyRepository by lazy { SafetyRepositoryImpl(api) }
    val chatRepository: ChatRepository by lazy {
        ChatRepositoryImpl(api, httpClient, tokenStore, appScope)
    }
}
