package app.befos.presentation.root

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.core.network.StoredAuth
import app.befos.domain.model.Interest
import app.befos.domain.model.Profile
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ProfileRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class RootViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val auth: AuthRepository = mockk(relaxed = true)
    private val profiles: ProfileRepository = mockk()

    private fun profile(name: String = "Иван", goal: String = "relationship", interests: Int = 2) = Profile(
        userId = "u1",
        name = name,
        age = 25,
        city = "Казань",
        gender = "male",
        about = null,
        datingGoal = goal,
        photoUrls = emptyList(),
        interests = List(interests) { Interest("slug-$it", "Интерес $it", "hobby") },
        lifestyle = emptyMap(),
        ageMin = 18,
        ageMax = 40,
        genderPreference = emptyList(),
    )

    private fun viewModel() = RootViewModel(auth, profiles).also {
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
    }

    @Test
    fun `without stored session routes to auth`() = runTest {
        coEvery { auth.current() } returns null
        assertEquals(RootDestination.AUTH, viewModel().destination.value)
    }

    @Test
    fun `completed profile routes straight to main`() = runTest {
        coEvery { auth.current() } returns StoredAuth("a", "r", "u1")
        coEvery { profiles.me() } returns ApiResult.Success(profile())
        assertEquals(RootDestination.MAIN, viewModel().destination.value)
    }

    @Test
    fun `incomplete profile routes to onboarding`() = runTest {
        coEvery { auth.current() } returns StoredAuth("a", "r", "u1")
        coEvery { profiles.me() } returns ApiResult.Success(profile(name = "", interests = 0))
        assertEquals(RootDestination.ONBOARDING, viewModel().destination.value)
    }

    @Test
    fun `a session the backend refused to refresh again routes to auth`() = runTest {
        // The client, not this ViewModel, decides that a session is over: a refresh the
        // server rejected clears the stored tokens before the 401 reaches here. Two reads
        // of `current()` are the whole story — present at the gate, gone after the 401.
        coEvery { auth.current() } returnsMany listOf(StoredAuth("a", "r", "u1"), null)
        coEvery { profiles.me() } returns ApiResult.Error(401, "unauthorized")
        assertEquals(RootDestination.AUTH, viewModel().destination.value)
        coVerify(exactly = 0) { auth.logout() }
    }

    @Test
    fun `a 401 the client could not have logged out over keeps the session`() = runTest {
        // An outage or a restarting backend fails the refresh without saying anything about
        // the session, and the retried call then answers 401 anyway. Erasing the tokens here
        // would sign a logged-in user out over a hiccup, which is the bug this pins shut.
        coEvery { auth.current() } returns StoredAuth("a", "r", "u1")
        coEvery { profiles.me() } returns ApiResult.Error(401, "unauthorized")
        assertEquals(RootDestination.MAIN, viewModel().destination.value)
        coVerify(exactly = 0) { auth.logout() }
    }

    @Test
    fun `transient backend failure keeps user inside main`() = runTest {
        coEvery { auth.current() } returns StoredAuth("a", "r", "u1")
        coEvery { profiles.me() } returns ApiResult.Error(503, "unavailable")
        assertEquals(RootDestination.MAIN, viewModel().destination.value)
        coVerify(exactly = 0) { auth.logout() }
    }
}
