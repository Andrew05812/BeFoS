package app.befos.presentation.settings

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Profile
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.SafetyRepository
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class SettingsViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val safety: SafetyRepository = mockk()
    private val auth: AuthRepository = mockk()
    private val profiles: ProfileRepository = mockk()

    private fun profile(hidden: Boolean) = Profile(
        userId = "me", name = "Анна", age = 29, city = "Москва", gender = "female",
        about = null, datingGoal = "relationship", photoUrls = emptyList(),
        interests = emptyList(), lifestyle = emptyMap(), ageMin = 25, ageMax = 35,
        genderPreference = emptyList(), isHidden = hidden,
    )

    @Test
    fun `a visibility check that never answered says the switch is unverified`() = runTest {
        coEvery { profiles.me() } returns ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The switch is drawn from a default here, and a hidden account looks exactly like a
        // visible one until the server says otherwise.
        assertEquals(false, vm.uiState.value.hidden)
        assertEquals(true, vm.uiState.value.visibilityUnknown)
    }

    @Test
    fun `a visibility check that answers puts the switch on the server's state`() = runTest {
        coEvery { profiles.me() } returns ApiResult.Success(profile(hidden = true))

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.hidden)
        assertEquals(false, vm.uiState.value.visibilityUnknown)
    }

    @Test
    fun `an answer the server confirms settles the warning`() = runTest {
        coEvery { profiles.me() } returns ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")
        coEvery { safety.setVisibility(false) } returns ApiResult.Success(Unit)

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.visibilityUnknown)

        vm.setHidden(false)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(false, vm.uiState.value.visibilityUnknown)
        assertEquals("Вы снова видны в подборе.", vm.uiState.value.message)
    }

    @Test
    fun `a retry of the check clears the warning when the server comes back`() = runTest {
        coEvery { profiles.me() } returnsMany listOf(
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
            ApiResult.Success(profile(hidden = true)),
        )

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.visibilityUnknown)

        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.hidden)
        assertEquals(false, vm.uiState.value.visibilityUnknown)
    }
}
