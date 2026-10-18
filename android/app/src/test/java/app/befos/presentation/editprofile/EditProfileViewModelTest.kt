package app.befos.presentation.editprofile

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Interest
import app.befos.domain.model.Profile
import app.befos.domain.model.ProfileUpdateData
import app.befos.domain.repository.ProfileRepository
import io.mockk.coEvery
import io.mockk.mockk
import io.mockk.slot
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
        about = null, datingGoal = "relationship", photos = emptyList(),
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

    @Test
    fun `the search city the server holds arrives in the field the person edits`() = runTest {
        coEvery { repo.me() } returns ApiResult.Success(profile().copy(cityPreference = "Тверь"))
        coEvery { repo.interests() } returns ApiResult.Success(interests)

        val vm = EditProfileViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The screen shows the stored filter rather than a default, so an empty field at the
        // moment of saving is the person's own erasure and nothing the screen invented.
        assertEquals("Тверь", vm.uiState.value.cityPreference)
    }

    @Test
    fun `a profile that never named a search city opens the field empty`() = runTest {
        coEvery { repo.me() } returns ApiResult.Success(profile())
        coEvery { repo.interests() } returns ApiResult.Success(interests)

        val vm = EditProfileViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("", vm.uiState.value.cityPreference)
    }

    @Test
    fun `saving sends the search city it was given`() = runTest {
        coEvery { repo.me() } returns ApiResult.Success(profile())
        coEvery { repo.interests() } returns ApiResult.Success(interests)
        val sent = slot<ProfileUpdateData>()
        coEvery { repo.update(capture(sent)) } returns ApiResult.Success(profile())

        val vm = EditProfileViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onCityPreferenceChange("  Тверь  ")
        vm.save()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("Тверь", sent.captured.cityPreference)
    }

    @Test
    fun `erasing the field is sent as the answer that removes the filter, not as an omission`() = runTest {
        coEvery { repo.me() } returns ApiResult.Success(profile().copy(cityPreference = "Тверь"))
        coEvery { repo.interests() } returns ApiResult.Success(interests)
        val sent = slot<ProfileUpdateData>()
        coEvery { repo.update(capture(sent)) } returns ApiResult.Success(profile())

        val vm = EditProfileViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onCityPreferenceChange("")
        vm.save()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Null would mean «не трогать» and the serializer drops it anyway; only the empty string
        // carries the erase to a server that cannot be reached with a JSON null from this client.
        assertEquals("", sent.captured.cityPreference)
    }
}
