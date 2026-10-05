package app.befos.presentation.profile

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Profile
import app.befos.domain.model.TestProgress
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.TestRepository
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class ProfileViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val profileRepo: ProfileRepository = mockk()
    private val testRepo: TestRepository = mockk()
    private val authRepo: AuthRepository = mockk {
        every { authState } returns emptyFlow()
    }

    private fun profile(name: String = "Анна") = Profile(
        userId = "me", name = name, age = 28, city = "Москва", gender = "female",
        about = "О себе", datingGoal = "relationship", photoUrls = emptyList(),
        interests = emptyList(), lifestyle = emptyMap(), ageMin = 25, ageMax = 35,
        genderPreference = listOf("male"),
    )

    private fun progress(percent: Int) = TestProgress(
        answered = percent, total = 100, percent = percent, remaining = 100 - percent,
        completed = percent >= 100,
    )

    private fun vm(): ProfileViewModel {
        coEvery { profileRepo.me() } returns ApiResult.Success(profile())
        coEvery { testRepo.progress() } returns ApiResult.Success(progress(40))
        val vm = ProfileViewModel(profileRepo, testRepo, authRepo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        return vm
    }

    @Test
    fun `a refresh that fails over a cached profile warns instead of blanking the tab`() = runTest {
        val vm = vm()
        coEvery { profileRepo.me() } returns ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")

        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("Анна", vm.uiState.value.profile?.name)
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.refreshError)
        assertEquals(null, vm.uiState.value.error)
    }

    @Test
    fun `a refresh that fails after the profile loads keeps the percent and says it may be old`() = runTest {
        val vm = vm()
        coEvery { testRepo.progress() } returns ApiResult.Error(-1, "Нет подключения к интернету.")

        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The card would otherwise read as a fresh answer count from a server that never answered.
        assertEquals(40, vm.uiState.value.testProgress?.percent)
        assertEquals("Нет подключения к интернету.", vm.uiState.value.refreshError)
        assertEquals(false, vm.uiState.value.testProgressFailed)
    }

    @Test
    fun `a progress failure with nothing cached keeps the card's own not-loaded state`() = runTest {
        coEvery { profileRepo.me() } returns ApiResult.Success(profile())
        coEvery { testRepo.progress() } returns ApiResult.Error(-1, "Нет подключения к интернету.")

        val vm = ProfileViewModel(profileRepo, testRepo, authRepo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.testProgressFailed)
        assertEquals(null, vm.uiState.value.testProgress)

        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Nothing was on screen to go stale, so the card state is the whole signal.
        assertEquals(true, vm.uiState.value.testProgressFailed)
        assertEquals(null, vm.uiState.value.refreshError)
    }

    @Test
    fun `a refresh that lands clears the warning`() = runTest {
        val vm = vm()
        coEvery { profileRepo.me() } returns ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")
        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Анна", vm.uiState.value.profile?.name)
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.refreshError)
        coEvery { profileRepo.me() } returns ApiResult.Success(profile("Анна К."))

        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("Анна К.", vm.uiState.value.profile?.name)
        assertEquals(null, vm.uiState.value.refreshError)
    }

    @Test
    fun `a refresh that fails with no profile cached is the screen error`() = runTest {
        coEvery { profileRepo.me() } returns ApiResult.Error(-1, "Сессия истекла. Войдите снова.")
        coEvery { testRepo.progress() } returns ApiResult.Error(401, "Сессия истекла. Войдите снова.")

        val vm = ProfileViewModel(profileRepo, testRepo, authRepo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(null, vm.uiState.value.profile)

        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The screen has nothing to show, so it names the failure rather than a stale notice.
        assertEquals("Сессия истекла. Войдите снова.", vm.uiState.value.error)
        assertEquals(true, vm.uiState.value.testProgressFailed)
        assertEquals(null, vm.uiState.value.refreshError)
    }
}
