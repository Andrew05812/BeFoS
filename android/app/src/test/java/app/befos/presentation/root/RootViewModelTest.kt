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

    private fun profile(
        name: String = "Иван",
        goal: String = "relationship",
        interests: Int = 2,
        onboarded: Boolean = true,
        // A finished account is a confirmed address and the text the product publishes today.
        // The gates get their own cases below; every other case here is about onboarding.
        verified: Boolean = true,
        consentCurrent: Boolean = true,
    ) = Profile(
        userId = "u1",
        name = name,
        age = 25,
        city = "Казань",
        gender = "male",
        about = null,
        datingGoal = goal,
        photos = emptyList(),
        interests = List(interests) { Interest("slug-$it", "Интерес $it", "hobby") },
        lifestyle = emptyMap(),
        ageMin = 18,
        ageMax = 40,
        genderPreference = emptyList(),
        onboardingCompleted = onboarded,
        emailVerified = verified,
        consentUpToDate = consentCurrent,
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
        // Так выглядит скорлупа, которую оставляет регистрация: имя взято из почты, цель стоит
        // дефолтная. По полям её от прошедшего онбординг не отличить — отличает только штамп сервера.
        coEvery { profiles.me() } returns ApiResult.Success(
            profile(name = "ivan", interests = 0, onboarded = false)
        )
        assertEquals(RootDestination.ONBOARDING, viewModel().destination.value)
    }

    @Test
    fun `a person who named no interests is not sent back to the form`() = runTest {
        coEvery { auth.current() } returns StoredAuth("a", "r", "u1")
        coEvery { profiles.me() } returns ApiResult.Success(
            profile(name = "Аня", interests = 0)
        )
        assertEquals(
            "онбординг принимает человека без интересов; правило, угадывающее по полям, " +
                "отправляет его в форму и отрезает от его же пары",
            RootDestination.MAIN,
            viewModel().destination.value,
        )
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
    fun `an unconfirmed address stops at the letter before onboarding`() = runTest {
        coEvery { auth.current() } returns StoredAuth("a", "r", "u1")
        coEvery { profiles.me() } returns ApiResult.Success(
            profile(onboarded = false, verified = false)
        )
        // A person who registered and never answered the letter is not sent into a questionnaire
        // that ends in a deck the server keeps them out of.
        assertEquals(RootDestination.EMAIL_CONFIRMATION, viewModel().destination.value)
    }

    @Test
    fun `a confirmed account that finished onboarding goes to main`() = runTest {
        coEvery { auth.current() } returns StoredAuth("a", "r", "u1")
        coEvery { profiles.me() } returns ApiResult.Success(
            profile(onboarded = true, verified = true)
        )
        assertEquals(RootDestination.MAIN, viewModel().destination.value)
    }

    @Test
    fun `a stale consent text is asked for before the address or the form`() = runTest {
        coEvery { auth.current() } returns StoredAuth("a", "r", "u1")
        coEvery { profiles.me() } returns ApiResult.Success(
            profile(onboarded = true, verified = false, consentCurrent = false)
        )
        // Both gates are open; the document is the one the person can settle on this screen, and
        // until it is accepted the product has no record of what they agreed to.
        assertEquals(RootDestination.CONSENT, viewModel().destination.value)
    }

    @Test
    fun `a session with the text accepted and the address confirmed is past both gates`() =
        runTest {
            coEvery { auth.current() } returns StoredAuth("a", "r", "u1")
            coEvery { profiles.me() } returns ApiResult.Success(
                profile(onboarded = false, verified = true, consentCurrent = true)
            )
            assertEquals(RootDestination.ONBOARDING, viewModel().destination.value)
        }

    @Test
    fun `transient backend failure keeps user inside main`() = runTest {
        coEvery { auth.current() } returns StoredAuth("a", "r", "u1")
        coEvery { profiles.me() } returns ApiResult.Error(503, "unavailable")
        assertEquals(RootDestination.MAIN, viewModel().destination.value)
        coVerify(exactly = 0) { auth.logout() }
    }
}
