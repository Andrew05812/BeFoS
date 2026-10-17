package app.befos.presentation.profile

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Profile
import app.befos.domain.model.ProfilePhoto
import app.befos.domain.model.TestProgress
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.TestRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * The owner's three writes to their own photograph row: take one away, lead with one, move one.
 *
 * What the server answers is the row it now holds, so the tab has to paint that answer and nothing
 * else. The checks here are about that promise and about the four ways a person can still break it:
 * tapping twice, asking twice, answering the removal question with «Отмена», and a background read
 * that left before the write did. A device is not needed for any of them — the picture chooser, the
 * pixels of a tile and the order they are drawn in are the screen's own business, checked by hand.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ProfilePhotoManagementTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val profileRepo: ProfileRepository = mockk()
    private val testRepo: TestRepository = mockk()
    private val authRepo: AuthRepository = mockk {
        every { authState } returns emptyFlow()
    }

    private fun profile(vararg ids: String) = Profile(
        userId = "me", name = "Анна", age = 28, city = "Москва", gender = "female",
        about = "О себе", datingGoal = "relationship",
        photos = ids.mapIndexed { index, id -> ProfilePhoto(id = id, url = "https://host/uploads/$id.jpg") },
        interests = emptyList(), lifestyle = emptyMap(), ageMin = 25, ageMax = 35,
        genderPreference = listOf("male"),
    )

    private fun idsOf(state: ProfileUiState) = state.profile?.photos?.map { it.id }.orEmpty()

    private fun row(photoIds: List<String>): Profile = profile(*photoIds.toTypedArray())

    private fun loaded(): ProfileViewModel = loaded("p1", "p2", "p3")

    private fun loaded(vararg ids: String): ProfileViewModel {
        coEvery { profileRepo.me() } returns ApiResult.Success(profile(*ids))
        coEvery { testRepo.progress() } returns ApiResult.Success(
            TestProgress(answered = 40, total = 100, percent = 40, remaining = 60, completed = false),
        )
        val vm = ProfileViewModel(profileRepo, testRepo, authRepo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        return vm
    }

    @Test
    fun `the question about a removal sends nothing until it is answered`() = runTest {
        val vm = loaded()

        vm.askDeletePhoto("p2")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("p2", vm.uiState.value.pendingDeletion)
        assertFalse("asking is not removing", vm.uiState.value.photoBusy)
        coVerify(exactly = 0) { profileRepo.deletePhoto(any()) }
    }

    @Test
    fun `backing out of the question leaves the row exactly as the server holds it`() = runTest {
        val vm = loaded()
        vm.askDeletePhoto("p2")

        vm.cancelDeletePhoto()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(null, vm.uiState.value.pendingDeletion)
        assertEquals(listOf("p1", "p2", "p3"), idsOf(vm.uiState.value))
        coVerify(exactly = 0) { profileRepo.deletePhoto(any()) }
    }

    @Test
    fun `an answer to the question removes one photograph and paints the row that came back`() = runTest {
        val vm = loaded()
        // The answer is the server's row, with the removed picture gone and the flag already moved on.
        coEvery { profileRepo.deletePhoto("p2") } returns ApiResult.Success(row(listOf("p1", "p3")))

        vm.askDeletePhoto("p2")
        vm.confirmDeletePhoto()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { profileRepo.deletePhoto("p2") }
        assertEquals(listOf("p1", "p3"), idsOf(vm.uiState.value))
        assertEquals(null, vm.uiState.value.pendingDeletion)
        assertEquals(null, vm.uiState.value.photoError)
        assertFalse(vm.uiState.value.photoBusy)
    }

    @Test
    fun `confirming without a question sends nothing`() = runTest {
        val vm = loaded()

        vm.confirmDeletePhoto()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 0) { profileRepo.deletePhoto(any()) }
        assertEquals(listOf("p1", "p2", "p3"), idsOf(vm.uiState.value))
    }

    @Test
    fun `the last photograph can go, and the empty row is the row the server answered`() = runTest {
        val vm = loaded("p1")
        coEvery { profileRepo.deletePhoto("p1") } returns ApiResult.Success(row(emptyList()))

        vm.askDeletePhoto("p1")
        vm.confirmDeletePhoto()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // No flag is set and no url is held: the hero falls back to initials and the tab's empty
        // copy is what the screen has to print, so the state must say «none» rather than «unknown».
        assertEquals(emptyList<String>(), idsOf(vm.uiState.value))
        assertEquals(null, vm.uiState.value.profile?.primaryPhoto)
        assertFalse(vm.uiState.value.photoBusy)
    }

    @Test
    fun `a refusal keeps the row standing and names what the server objected to`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.deletePhoto("p9") } returns
            ApiResult.Error(404, "Этого снимка в вашем профиле нет. Обновите экран.")

        // The removal asked about is not in the row; the write is issued anyway and refused, which is
        // the honest path — the screen does not decide on its own that a photograph is somebody else's.
        vm.askDeletePhoto("p9")
        vm.confirmDeletePhoto()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("Этого снимка в вашем профиле нет. Обновите экран.", vm.uiState.value.photoError)
        assertEquals(listOf("p1", "p2", "p3"), idsOf(vm.uiState.value))
        assertFalse("a refused write is over; the next tap may start one", vm.uiState.value.photoBusy)
    }

    @Test
    fun `one write to the row travels at a time`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.reorderPhotos(any()) } returns ApiResult.Success(row(listOf("p1", "p3", "p2")))

        vm.movePhoto("p2", 1)
        assertTrue("the reorder is in flight", vm.uiState.value.photoBusy)
        vm.movePhoto("p3", 1)
        vm.makePhotoPrimary("p1")
        vm.askDeletePhoto("p2")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { profileRepo.reorderPhotos(any()) }
        coVerify(exactly = 0) { profileRepo.makePhotoPrimary(any()) }
        coVerify(exactly = 0) { profileRepo.deletePhoto(any()) }
        // A question asked while a write is landing is a question the screen cannot answer yet.
        assertEquals(null, vm.uiState.value.pendingDeletion)
    }

    @Test
    fun `a lead that is already the lead sends nothing`() = runTest {
        val vm = loaded()

        vm.makePhotoPrimary("p1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 0) { profileRepo.makePhotoPrimary(any()) }
        assertFalse(vm.uiState.value.photoBusy)
    }

    @Test
    fun `leading with a photograph paints the row the answer carries, with one flag`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.makePhotoPrimary("p3") } returns
            ApiResult.Success(row(listOf("p3", "p1", "p2")))

        vm.makePhotoPrimary("p3")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The client does not move the head itself: `is_primary` is the server's row written from one
        // list, and the answer is the only copy of it this screen keeps.
        assertEquals("https://host/uploads/p3.jpg", vm.uiState.value.profile?.primaryPhoto)
        assertEquals(listOf("p3", "p1", "p2"), idsOf(vm.uiState.value))
        assertEquals(null, vm.uiState.value.photoError)
    }

    @Test
    fun `a move sends the whole row it holds, not the pair that swapped`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.reorderPhotos(any()) } returns ApiResult.Success(row(listOf("p1", "p3", "p2")))

        vm.movePhoto("p3", -1)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { profileRepo.reorderPhotos(listOf("p1", "p3", "p2")) }
        assertEquals(listOf("p1", "p3", "p2"), idsOf(vm.uiState.value))
    }

    @Test
    fun `a move with nowhere to go, and a move of a photograph not held, are both silent`() = runTest {
        val vm = loaded()

        vm.movePhoto("p1", -1)
        vm.movePhoto("p3", 1)
        vm.movePhoto("p7", 1)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The buttons that would do this are disabled on the screen, so a call reaching the view model
        // with nowhere to move is a stale tap or a list that changed underneath it. Neither is a write.
        coVerify(exactly = 0) { profileRepo.reorderPhotos(any()) }
        assertEquals(listOf("p1", "p2", "p3"), idsOf(vm.uiState.value))
    }

    @Test
    fun `a reorder the server refuses leaves the order on screen unchanged`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.reorderPhotos(any()) } returns
            ApiResult.Error(422, "Список снимков изменился. Обновите экран и переставьте заново.")

        vm.movePhoto("p3", -1)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The screen keeps the server's order rather than the order the person tapped for: a half-applied
        // permutation on screen would be the desync the route itself refuses to write.
        assertEquals(listOf("p1", "p2", "p3"), idsOf(vm.uiState.value))
        assertEquals("Список снимков изменился. Обновите экран и переставьте заново.", vm.uiState.value.photoError)
    }

    @Test
    fun `a lost connection reads as a lost connection`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.reorderPhotos(any()) } returns
            ApiResult.Error(-1, "Нет подключения к интернету.")

        vm.movePhoto("p2", 1)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("Нет подключения к интернету.", vm.uiState.value.photoError)
        assertFalse(vm.uiState.value.photoBusy)
    }

    @Test
    fun `a write clears a refusal it follows`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.reorderPhotos(any()) } returns ApiResult.Error(404, "Этого снимка в вашем профиле нет. Обновите экран.")
        vm.movePhoto("p2", 1)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.photoError != null)

        coEvery { profileRepo.reorderPhotos(any()) } returns ApiResult.Success(row(listOf("p2", "p1", "p3")))
        vm.movePhoto("p2", -1)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(null, vm.uiState.value.photoError)
        assertEquals(listOf("p2", "p1", "p3"), idsOf(vm.uiState.value))
    }

    @Test
    fun `a read that left before a write does not repaint the older row`() = runTest {
        val vm = loaded()
        // The silent refresh leaves with a read the test holds open, so it can land after a write does.
        val held = CompletableDeferred<ApiResult<Profile>>()
        coEvery { profileRepo.me() } coAnswers { held.await() }
        coEvery { profileRepo.deletePhoto("p1") } returns ApiResult.Success(row(listOf("p2", "p3")))

        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.askDeletePhoto("p1")
        vm.confirmDeletePhoto()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("p2", "p3"), idsOf(vm.uiState.value))

        // The row this read was handed is the one from before the removal, and it arrives last.
        held.complete(ApiResult.Success(row(listOf("p1", "p2", "p3"))))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("a read older than the write's answer must not put a removed photograph back",
            listOf("p2", "p3"), idsOf(vm.uiState.value))
    }

    @Test
    fun `a silent refresh does not start while a write to the row is landing`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.reorderPhotos(any()) } returns ApiResult.Success(row(listOf("p1", "p3", "p2")))

        vm.movePhoto("p2", 1)
        assertTrue(vm.uiState.value.photoBusy)
        vm.refreshSilently()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { profileRepo.me() }
        assertEquals(listOf("p1", "p3", "p2"), idsOf(vm.uiState.value))
    }

    @Test
    fun `the questionnaire and the identity rows survive a write to the photograph row`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.deletePhoto("p2") } returns ApiResult.Success(row(listOf("p1", "p3")))

        vm.askDeletePhoto("p2")
        vm.confirmDeletePhoto()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The answer carries the whole profile, so nothing else is asked again: the percent and the
        // name stay where the first read put them, and no second round trip is paid for them.
        assertEquals(40, vm.uiState.value.testProgress?.percent)
        assertEquals("Анна", vm.uiState.value.profile?.name)
        coVerify(exactly = 1) { profileRepo.me() }
    }
}
