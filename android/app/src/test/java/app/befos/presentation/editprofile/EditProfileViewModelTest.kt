package app.befos.presentation.editprofile

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
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class EditProfileViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val repo: ProfileRepository = mockk()

    private val interests = listOf(
        Interest(slug = "kino", name = "Кино", category = "culture"),
        Interest(slug = "hiking", name = "Походы", category = "sport"),
    )

    private fun profile() = Profile(
        userId = "me", name = "Анна", age = 29, city = "Москва", gender = "female",
        about = null, datingGoal = "relationship", photoUrls = emptyList(),
        interests = emptyList(), lifestyle = emptyMap(), ageMin = 25, ageMax = 35,
        genderPreference = emptyList(),
    )

    @Test
    fun `an empty picker says the catalogue did not load`() = runTest {
        coEvery { repo.me() } returns ApiResult.Success(profile())
        coEvery { repo.interests() } returns ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")

        val vm = EditProfileViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Nothing under the "Интересы" heading otherwise reads as a profile that has none.
        assertTrue(vm.uiState.value.allInterests.isEmpty())
        assertEquals(true, vm.uiState.value.interestsFailed)
    }

    @Test
    fun `retrying the catalogue fills the picker and clears the warning`() = runTest {
        coEvery { repo.me() } returns ApiResult.Success(profile())
        coEvery { repo.interests() } returnsMany listOf(
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
            ApiResult.Success(interests),
        )

        val vm = EditProfileViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.interestsFailed)

        vm.loadInterests()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("kino", "hiking"), vm.uiState.value.allInterests.map { it.slug })
        assertEquals(false, vm.uiState.value.interestsFailed)
    }

    @Test
    fun `retrying the catalogue leaves the typed answer alone`() = runTest {
        coEvery { repo.me() } returns ApiResult.Success(profile())
        coEvery { repo.interests() } returnsMany listOf(
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
            ApiResult.Success(interests),
        )

        val vm = EditProfileViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onNameChange("Анна К.")
        vm.onAboutChange("Пишу здесь, и не хочу это потерять.")

        vm.loadInterests()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // A retry of one read must not re-read the profile and overwrite the form.
        assertEquals("Анна К.", vm.uiState.value.name)
        assertEquals("Пишу здесь, и не хочу это потерять.", vm.uiState.value.about)
        assertEquals(2, vm.uiState.value.allInterests.size)
    }
}
