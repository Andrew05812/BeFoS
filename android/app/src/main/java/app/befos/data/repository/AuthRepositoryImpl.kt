package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.StoredAuth
import app.befos.core.network.TokenStore
import app.befos.core.network.map
import app.befos.data.mapper.toDomain
import app.befos.data.model.TokenPairDto
import app.befos.data.remote.ApiService
import app.befos.domain.model.SessionsPage
import app.befos.domain.repository.AuthRepository
import kotlinx.coroutines.flow.Flow

class AuthRepositoryImpl(
    private val api: ApiService,
    private val tokenStore: TokenStore,
) : AuthRepository {

    override val authState: Flow<StoredAuth?> = tokenStore.auth

    override suspend fun current(): StoredAuth? = tokenStore.current()

    override suspend fun lastEmail(): String? = tokenStore.lastEmail()

    override suspend fun register(email: String, password: String): ApiResult<String> {
        val result = api.register(email, password)
        return when (result) {
            is ApiResult.Success -> {
                persist(result.data.tokens, result.data.user.id, email)
                ApiResult.Success(result.data.user.id)
            }
            is ApiResult.Error -> result
        }
    }

    override suspend fun login(email: String, password: String): ApiResult<String> {
        val result = api.login(email, password)
        return when (result) {
            is ApiResult.Success -> {
                persist(result.data.tokens, result.data.user.id, email)
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

    /**
     * The server keeps no session after a changed word — this device's included — so the stored pair
     * is dropped on the success rather than left for the next refresh to fail on. A token the backend
     * has already revoked cannot reopen anything, and a screen that still holds it would keep
     * reporting a session it no longer has.
     */
    override suspend fun changePassword(
        oldPassword: String,
        newPassword: String,
        passwordConfirm: String,
    ): ApiResult<Unit> {
        val result = api.changePassword(oldPassword, newPassword, passwordConfirm)
        if (result is ApiResult.Success) tokenStore.clear()
        return result
    }

    override suspend fun sessions(): ApiResult<SessionsPage> =
        api.sessions().map { it.toDomain() }

    /**
     * Ends the row and leaves this device's tokens alone, whatever the answer was.
     *
     * The screen is the one that knows which row the server labelled as its own, and the repository has
     * no way to read that label out of a 204 — so dropping the stored pair here would mean guessing,
     * and a wrong guess logs a signed-in person out of a session the server never touched.
     */
    override suspend fun endSession(sessionId: String): ApiResult<Unit> = api.revokeSession(sessionId)

    override suspend fun endEverySession(): ApiResult<Unit> {
        val result = api.revokeAllSessions()
        if (result is ApiResult.Success) tokenStore.clear()
        return result
    }

    private suspend fun persist(tokens: TokenPairDto, userId: String, email: String) {
        tokenStore.save(StoredAuth(tokens.accessToken, tokens.refreshToken, userId), email.trim())
    }
}
