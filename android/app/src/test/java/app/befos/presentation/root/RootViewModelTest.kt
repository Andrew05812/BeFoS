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
    fun `expired session logs out and routes to auth`() = runTest {
        coEvery { auth.current() } returns StoredAuth("a", "r", "u1")
        coEvery { profiles.me() } returns ApiResult.Error(401, "unauthorized")
        assertEquals(RootDestination.AUTH, viewModel().destination.value)
        coVerify(exactly = 1) { auth.logout() }
    }

    @Test
    fun `transient backend failure keeps user inside main`() = runTest {
        coEvery { auth.current() } returns StoredAuth("a", "r", "u1")
        coEvery { profiles.me() } returns ApiResult.Error(503, "unavailable")
        assertEquals(RootDestination.MAIN, viewModel().destination.value)
        coVerify(exactly = 0) { auth.logout() }
    }
}
