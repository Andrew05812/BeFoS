package app.befos.core.network

import app.befos.BuildConfig
import app.befos.data.model.AuthResponseDto
import app.befos.data.model.RefreshRequest
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.auth.Auth
import io.ktor.client.plugins.auth.providers.BearerTokens
import io.ktor.client.plugins.auth.providers.bearer
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.plugins.defaultRequest
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.json.Json

object ApiConfig {
    const val BASE_URL: String = BuildConfig.API_BASE_URL
    const val WS_BASE_URL: String = BuildConfig.WS_BASE_URL
    const val API_PREFIX: String = "api/v1"

    /** Resolves a backend-relative path (e.g. ``/uploads/x.png``) to an absolute URL. */
    fun absolute(url: String?): String? {
        if (url.isNullOrBlank()) return null
        if (url.startsWith("http://") || url.startsWith("https://")) return url
        val base = BASE_URL.trimEnd('/')
        val path = if (url.startsWith("/")) url else "/$url"
        return base + path
    }

    fun wsUrl(matchId: String): String {
        val base = WS_BASE_URL.trimEnd('/')
        return "$base/ws/chat/$matchId"
    }
}

val befosJson = Json {
    ignoreUnknownKeys = true
    explicitNulls = false
    encodeDefaults = false
    coerceInputValues = true
    isLenient = true
}

fun createHttpClient(tokenStore: TokenStore): HttpClient = HttpClient(OkHttp) {
    expectSuccess = false

    install(ContentNegotiation) {
        json(befosJson)
    }

    install(WebSockets)

    install(Auth) {
        bearer {
            loadTokens {
                tokenStore.current()?.let { BearerTokens(it.accessToken, it.refreshToken) }
            }
            refreshTokens {
                val current = tokenStore.current() ?: return@refreshTokens null
                val response = client.post("${ApiConfig.BASE_URL}${ApiConfig.API_PREFIX}/auth/refresh") {
                    contentType(ContentType.Application.Json)
                    setBody(RefreshRequest(current.refreshToken))
                    markAsRefreshTokenRequest()
                }
                if (response.status.value !in 200..299) {
                    tokenStore.clear()
                    return@refreshTokens null
                }
                val tokens = response.body<AuthResponseDto>().tokens
                tokenStore.updateTokens(tokens.accessToken, tokens.refreshToken)
                BearerTokens(tokens.accessToken, tokens.refreshToken)
            }
            sendWithoutRequest { request ->
                val path = request.url.buildString()
                !path.contains("/auth/login") &&
                    !path.contains("/auth/register") &&
                    !path.contains("/auth/refresh")
            }
        }
    }

    defaultRequest {
        contentType(ContentType.Application.Json)
        header("Accept", "application/json")
    }
}
