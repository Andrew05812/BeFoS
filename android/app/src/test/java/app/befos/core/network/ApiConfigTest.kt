package app.befos.core.network

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The base URL of a release build is typed by a human into an environment variable, and
 * both forms — with and without the trailing slash — have to produce the same route. One
 * call site used to concatenate the two by hand, so a base without its slash asked
 * `https://api.example.comapi/v1/auth/refresh`: only the refresh broke, only on the build
 * nobody ran, and every expired session ended in a logout.
 */
class ApiConfigTest {

    @Test
    fun `a base url joins a path with exactly one slash either way`() {
        for (base in listOf("https://api.befos.app", "https://api.befos.app/")) {
            assertEquals("https://api.befos.app/api/v1/auth/refresh", ApiConfig.joinUrl(base, "api/v1/auth/refresh"))
        }
        assertEquals(
            "https://api.befos.app/uploads/a.png",
            ApiConfig.joinUrl("https://api.befos.app/", "/uploads/a.png"),
        )
    }

    @Test
    fun `every url the client dials is built through the same join`() {
        // Pinned as shapes rather than the configured host: a mangled join always shows up
        // as a missing separator or a doubled one.
        val refresh = ApiConfig.api("auth/refresh")
        assertEquals(false, refresh.contains("//api"))
        assertEquals(false, refresh.contains("://api"))
        assertEquals(true, refresh.endsWith("/api/v1/auth/refresh"))

        val socket = ApiConfig.wsUrl("match-1")
        assertEquals(true, socket.endsWith("/ws/chat/match-1"))
        assertEquals(false, socket.contains("//ws"))

        val picture = ApiConfig.absolute("/uploads/a.png")
        assertEquals(true, picture!!.endsWith("/uploads/a.png"))
        assertEquals("https://cdn.example.com/a.png", ApiConfig.absolute("https://cdn.example.com/a.png"))
        assertEquals(null, ApiConfig.absolute("  "))
    }
}
