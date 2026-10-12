package app.befos.presentation.onboarding

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Interest
import app.befos.domain.model.Profile
import app.befos.domain.repository.ProfileRepository
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * The third onboarding step cannot be passed without the interest catalogue: the server
 * requires three slugs of its own list, and the chip row is the only way to pick them. So a
 * failed `GET /api/v1/users/interests` is not a cosmetic hiccup — it is the whole flow, and
 * the step used to answer it with an empty box and "Выберите минимум 3 интереса."
 */
@OptIn(ExperimentalCoroutinesApi::class)
class OnboardingViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val repo: ProfileRepository = mockk()

    private val unavailable =
        ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")

    private val catalogue = listOf(
        Interest(slug = "kino", name = "Кино", category = "culture"),
        Interest(slug = "hiking", name = "Походы", category = "sport"),
        Interest(slug = "muzyka", name = "Музыка", category = "culture"),
    )

    /** What the server hands back for a profile that has been written. */
    private fun savedProfile(): Profile = Profile(
        userId = "me", name = "Вера", age = 29, city = "Москва", gender = "female",
        about = null, datingGoal = "relationship", photoUrls = emptyList(),
        interests = emptyList(), lifestyle = emptyMap(), ageMin = 20, ageMax = 45,
        genderPreference = emptyList(),
    )

    /** A person who filled steps 1 and 2 and is standing on the interests step. */
    private fun reachedInterestsStep(): OnboardingViewModel {
        coEvery { repo.interests() } returns unavailable
        val vm = OnboardingViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onNameChange("Вера")
        vm.onBirthDateChange("19960510")
        vm.onCityChange("Москва")
        vm.next()
        vm.next()
        assertEquals(2, vm.uiState.value.step)
        return vm
    }

    @Test
    fun `a catalogue that never loaded is named as a failure`() = runTest {
        val vm = reachedInterestsStep()

        assertTrue(vm.uiState.value.interestsFailed)
        assertFalse(vm.uiState.value.interestsLoading)
        assertEquals(emptyList<Interest>(), vm.uiState.value.interests)
    }

    @Test
    fun `a catalogue that never loaded is not blamed on the person`() = runTest {
        val vm = reachedInterestsStep()

        vm.next()

        // "Выберите минимум 3 интереса" tells someone who cannot see a single chip to look
        // harder at a list that is not there.
        assertEquals("Список интересов не загрузился. Повторите попытку.", vm.uiState.value.error)
    }

    @Test
    fun `too few chips from a loaded catalogue still says choose more`() = runTest {
        coEvery { repo.interests() } returns ApiResult.Success(catalogue)
        val vm = OnboardingViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onNameChange("Вера")
        vm.onBirthDateChange("19960510")
        vm.onCityChange("Москва")
        vm.next()
        vm.next()
        vm.toggleInterest("kino")

        vm.next()

        assertEquals("Выберите минимум 3 интереса.", vm.uiState.value.error)
    }

    @Test
    fun `retrying the catalogue fills the picker and clears the warning`() = runTest {
        val vm = reachedInterestsStep()
        coEvery { repo.interests() } returns ApiResult.Success(catalogue)

        vm.loadInterests()
        assertTrue(vm.uiState.value.interestsLoading)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(3, vm.uiState.value.interests.size)
        assertFalse(vm.uiState.value.interestsFailed)
    }

    @Test
    fun `retrying the catalogue leaves the typed answers alone`() = runTest {
        val vm = reachedInterestsStep()
        coEvery { repo.interests() } returns ApiResult.Success(catalogue)

        vm.loadInterests()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Steps 1 and 2 live only in this ViewModel, so a retry that re-reads them from the
        // server — or resets the form — throws away what the person typed.
        assertEquals("Вера", vm.uiState.value.name)
        assertEquals("Москва", vm.uiState.value.city)
        assertEquals(2, vm.uiState.value.step)
        assertEquals(3, vm.uiState.value.interests.size)
    }

    @Test
    fun `the step passed on a retry is the step that can be finished`() = runTest {
        val vm = reachedInterestsStep()
        coEvery { repo.interests() } returns ApiResult.Success(catalogue)
        vm.loadInterests()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        coEvery { repo.onboarding(any()) } returns ApiResult.Success(savedProfile())

        vm.toggleInterest("kino")
        vm.toggleInterest("hiking")
        vm.toggleInterest("muzyka")
        vm.next()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.done)
    }
}
