package app.befos.core.network

import app.befos.BuildConfig
import app.befos.data.model.RefreshRequest
import app.befos.data.model.TokenPairDto
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.HttpClientEngine
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.plugins.api.SendingRequest
import io.ktor.client.plugins.api.createClientPlugin
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
import io.ktor.http.HttpHeaders
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

/** Routes that are answered without a session, so no bearer token belongs on them. */
internal fun isPublicAuthRoute(url: String): Boolean =
    url.contains("/auth/login") || url.contains("/auth/register") || url.contains("/auth/refresh")

/**
 * Which token leaves the device is decided by the session, not by what the bearer provider
 * happened to remember: that provider caches the first token it loaded, and no DataStore write
 * invalidates the cache. Signing out, or signing in as somebody else without restarting the
 * process, therefore kept sending the previous account's token — the backend answered for the
 * wrong user while the interface showed the new one.
 *
 * Runs at the last moment before the request goes out, which is also after the retry that
 * follows a refresh: a retried request never re-enters the request hooks.
 */
private fun currentSessionBearer(tokens: SessionTokens) = createClientPlugin("CurrentSessionBearer") {
    on(SendingRequest) { request, _ ->
        if (isPublicAuthRoute(request.url.buildString())) return@on
        val accessToken = tokens.current()?.accessToken
        if (accessToken == null) {
            request.headers.remove(HttpHeaders.Authorization)
        } else {
            request.headers.set(HttpHeaders.Authorization, "Bearer $accessToken")
        }
    }
}

fun createHttpClient(
    tokens: SessionTokens,
    engine: HttpClientEngine = OkHttp.create(),
): HttpClient = HttpClient(engine) {
    expectSuccess = false

    // Every phase this client can wait in is named here, because only the connect used to be.
    // Measured on this stack (JVM, Ktor 3.0.1 + OkHttp): a server that accepts the connection and
    // stays silent was cut at 10 063 ms by an inherited engine default — the failure itself said
    // `socket_timeout=unknown` — while a response that trickles under that default was not cut at
    // all (still reading at 80 034 ms). The socket line declares the ten seconds that were already
    // in force, so nothing here changes how long the app waits; it changes what the wait is called,
    // and the ceiling is the app's first bound on a whole call. It sits above the backend's
    // measured queue hold (30.002 / 30.004 / 30.007 s, docs/OPERATIONS.md §7) and does not buy the
    // patience to wait that out: a queued request sends no bytes, so the ten-second silence line
    // ends it first — derived from the two measured numbers above, not run against an exhausted
    // pool. Widening that line to 30 s would trade a failure the user can retry at once for a
    // half-minute spinner, and this stage leaves the choice where the default had put it. A body
    // this client is not meant to deliver in seconds raises both numbers per request — see
    // ApiService.uploadPhoto.
    install(HttpTimeout) {
        connectTimeoutMillis = 5_000
        socketTimeoutMillis = 10_000
        requestTimeoutMillis = 35_000
    }

    install(ContentNegotiation) {
        json(befosJson)
    }

    // Installed because a chat connection needs a heartbeat, but what it delivers here is not
    // measured: against a peer that accepts the handshake and then says nothing, a pending read of
    // 60 s produced eight bytes on the wire — a masked Close(1000), sent when the session was
    // cancelled — and no PING at all. So `ChatSocket` reconnects on real read failures (close
    // frame, transport error, failed handshake), not on a ping timeout, and a black-holed socket is
    // not known to surface on its own.
    install(WebSockets) {
        pingIntervalMillis = 10_000
    }

    install(Auth) {
        bearer {
            loadTokens {
                tokens.current()?.let { BearerTokens(it.accessToken, it.refreshToken) }
            }
            refreshTokens {
                val current = tokens.current() ?: return@refreshTokens null
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
                    tokens.clear()
                    return@refreshTokens null
                }
                if (status !in 200..299) return@refreshTokens null
                // A proxy or a half-broken server can answer with HTML where a TokenPair is due.
                val pair = runCatching { response.body<TokenPairDto>() }.getOrNull()
                    ?: return@refreshTokens null
                tokens.updateTokens(pair.accessToken, pair.refreshToken)
                BearerTokens(pair.accessToken, pair.refreshToken)
            }
            sendWithoutRequest { request ->
                !isPublicAuthRoute(request.url.buildString())
            }
        }
    }

    install(currentSessionBearer(tokens))

    defaultRequest {
        contentType(ContentType.Application.Json)
        header("Accept", "application/json")
    }
}
