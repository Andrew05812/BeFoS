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
import io.ktor.client.HttpClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

class AppContainer(context: Context) {
    val appScope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val tokenStore: TokenStore = TokenStore(context.applicationContext)
    val httpClient: HttpClient = createHttpClient(tokenStore)
    private val api: ApiService = ApiService(httpClient)

    val authRepository: AuthRepository = AuthRepositoryImpl(api, tokenStore)
    val profileRepository: ProfileRepository = ProfileRepositoryImpl(api)
    val testRepository: TestRepository = TestRepositoryImpl(api)
    val discoveryRepository: DiscoveryRepository = DiscoveryRepositoryImpl(api)
    val matchRepository: MatchRepository = MatchRepositoryImpl(api)
    val safetyRepository: SafetyRepository = SafetyRepositoryImpl(api)
    val chatRepository: ChatRepository =
        ChatRepositoryImpl(api, httpClient, tokenStore, appScope)
}
