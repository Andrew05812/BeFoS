package app.befos.presentation.root

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * One root gate per launch.
 *
 * Measured on the stand: a cold start answered the gate twice — two `RootViewModel` objects
 * (02:00:57, hashes 8764458 authored by `BeFosNavHost` and 103792039 by `SplashScreen`), each
 * reading the profile. Two `GET /api/v1/users/me` per launch, and four plus a refresh once the
 * access token had expired (01:54:53). A ViewModel lives in the store of whoever asked for it,
 * and a nav entry has its own store, so a screen that builds a gate instead of taking one
 * doubles the read that decides where the launch goes.
 *
 * A unit test has no Compose runtime to compose a screen with, so this pins the shape that
 * makes the second gate impossible rather than its behaviour: the splash screen is handed the
 * gate, and nothing else in its signature can produce one.
 */
class RootGateOwnershipTest {

    private fun parameterTypes(functionClass: String, methodName: String): List<Class<*>> =
        Class.forName(functionClass).declaredMethods
            .single { it.name == methodName || it.name.startsWith("$methodName-") }
            .parameterTypes
            .toList()

    @Test
    fun `the splash screen receives the gate instead of building one`() {
        val gates = parameterTypes("app.befos.presentation.root.SplashScreenKt", "SplashScreen")
            .filter { RootViewModel::class.java.isAssignableFrom(it) }
        assertEquals(listOf(RootViewModel::class.java), gates)
    }
}
