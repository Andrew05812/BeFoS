package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.StoredAuth
import app.befos.core.network.TokenStore
import app.befos.data.remote.ApiService
import app.befos.domain.repository.AuthRepository
import kotlinx.coroutines.flow.Flow

class AuthRepositoryImpl(
    private val api: ApiService,
    private val tokenStore: TokenStore,
) : AuthRepository {

    override val authState: Flow<StoredAuth?> = tokenStore.auth

    override suspend fun current(): StoredAuth? = tokenStore.current()

    override suspend fun register(email: String, password: String): ApiResult<String> {
        val result = api.register(email, password)
        return when (result) {
            is ApiResult.Success -> {
                persist(result.data.tokens.accessToken, result.data.tokens.refreshToken, result.data.user.id)
                ApiResult.Success(result.data.user.id)
            }
            is ApiResult.Error -> result
        }
    }

    override suspend fun login(email: String, password: String): ApiResult<String> {
        val result = api.login(email, password)
        return when (result) {
            is ApiResult.Success -> {
                persist(result.data.tokens.accessToken, result.data.tokens.refreshToken, result.data.user.id)
                ApiResult.Success(result.data.user.id)
            }
            is ApiResult.Error -> result
        }
    }

    override suspend fun logout() {
        val refresh = tokenStore.current()?.refreshToken
        if (refresh != null) runCatching { api.logout(refresh) }
        tokenStore.clear()
    }

    private suspend fun persist(access: String, refresh: String, userId: String) {
        tokenStore.save(StoredAuth(access, refresh, userId))
    }
}
