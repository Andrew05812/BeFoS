package app.befos.core.network

import app.befos.BuildConfig
import app.befos.data.model.RefreshRequest
import app.befos.data.model.TokenPairDto
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpTimeout
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

    /** Full URL of an API route, e.g. ``api("users/me")``. */
    fun api(path: String): String = joinUrl(BASE_URL, "$API_PREFIX/$path")

    /** Resolves a backend-relative path (e.g. ``/uploads/x.png``) to an absolute URL. */
    fun absolute(url: String?): String? {
        if (url.isNullOrBlank()) return null
        if (url.startsWith("http://") || url.startsWith("https://")) return url
        return joinUrl(BASE_URL, url)
    }

    fun wsUrl(matchId: String): String = joinUrl(WS_BASE_URL, "ws/chat/$matchId")

    /**
     * The one place a base URL and a path are joined. `BEFOS_API_BASE_URL` is written by a
     * human into a release build, and a base without its trailing slash used to produce
     * `https://api.example.comapi/v1/...` for the refresh call only: the token could not be
     * refreshed, so an expired session logged the user out on the one build nobody tested.
     */
    internal fun joinUrl(base: String, path: String): String =
        base.trimEnd('/') + "/" + path.trimStart('/')
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

    // Fail fast when the backend is unreachable; the socket defaults hang for ~10s each,
    // which turns a cold start without network into a minute of blank splash.
    install(HttpTimeout) {
        connectTimeoutMillis = 5_000
    }

    install(ContentNegotiation) {
        json(befosJson)
    }

    // Keepalive pings surface half-open sockets (abrupt server loss) as failures,
    // so the chat reconnect loop can actually restart instead of hanging on read.
    install(WebSockets) {
        pingIntervalMillis = 10_000
    }

    install(Auth) {
        bearer {
            loadTokens {
                tokenStore.current()?.let { BearerTokens(it.accessToken, it.refreshToken) }
            }
            refreshTokens {
                val current = tokenStore.current() ?: return@refreshTokens null
                // A refresh fails for reasons that say nothing about the session: the backend is
                // restarting, the network dropped, the auth limiter tripped. Erasing the stored
                // tokens on any of those logs a signed-in user out over a transient hiccup, so
                // only an explicit authorization rejection is allowed to end the session.
                val response = try {
                    client.post(ApiConfig.api("auth/refresh")) {
                        contentType(ContentType.Application.Json)
                        setBody(RefreshRequest(current.refreshToken))
                        markAsRefreshTokenRequest()
                    }
                } catch (_: Exception) {
                    return@refreshTokens null
                }
                val status = response.status.value
                if (status == 401 || status == 403) {
                    tokenStore.clear()
                    return@refreshTokens null
                }
                if (status !in 200..299) return@refreshTokens null
                // A proxy or a half-broken server can answer with HTML where a TokenPair is due.
                val tokens = runCatching { response.body<TokenPairDto>() }.getOrNull()
                    ?: return@refreshTokens null
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
