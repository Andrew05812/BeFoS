package app.befos.presentation.profile

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.core.network.PHOTO_TYPES_SUPPORTED
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
import java.io.ByteArrayInputStream
import java.io.FileNotFoundException
import java.io.InputStream
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * The person's own photograph, from the picker to the tab.
 *
 * What a device would have to show is decided here instead: which picture the tab paints after a
 * send, what a refusal costs the screen, and which files never reach the uplink at all. The bytes
 * themselves are a stream the test hands over, because the tab's job starts where the system's
 * content uri ends.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ProfilePhotoUploadTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val profileRepo: ProfileRepository = mockk()
    private val testRepo: TestRepository = mockk()
    private val authRepo: AuthRepository = mockk {
        every { authState } returns emptyFlow()
    }

    private fun profile(vararg photos: String) = Profile(
        userId = "me", name = "Анна", age = 28, city = "Москва", gender = "female",
        about = "О себе", datingGoal = "relationship",
        photos = photos.mapIndexed { index, url -> ProfilePhoto(id = "photo-$index", url = url) },
        interests = emptyList(), lifestyle = emptyMap(), ageMin = 25, ageMax = 35,
        genderPreference = listOf("male"),
    )

    private fun stream() = ByteArrayInputStream("bytes of a photo".toByteArray())

    private fun loaded(): ProfileViewModel {
        coEvery { profileRepo.me() } returns ApiResult.Success(profile("https://host/uploads/old.jpg"))
        coEvery { testRepo.progress() } returns ApiResult.Success(
            TestProgress(answered = 40, total = 100, percent = 40, remaining = 60, completed = false),
        )
        val vm = ProfileViewModel(profileRepo, testRepo, authRepo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        return vm
    }

    @Test
    fun `the photograph the server took is the one the tab paints`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.uploadPhoto(any(), any()) } returns
            ApiResult.Success(profile("https://host/uploads/new.jpg", "https://host/uploads/old.jpg"))

        vm.uploadPhoto("image/jpeg") { stream() }
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The list arrives from the answer: the route re-encoded the file, named it itself, and put
        // the new picture first. Nothing on screen was assembled from the bytes that were sent.
        assertEquals("https://host/uploads/new.jpg", vm.uiState.value.profile?.primaryPhoto)
        assertEquals(2, vm.uiState.value.profile?.photoUrls?.size)
        assertEquals(null, vm.uiState.value.uploadError)
        assertFalse(vm.uiState.value.uploading)
    }

    @Test
    fun `a picture that landed is painted from the answer rather than a second read`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.uploadPhoto(any(), any()) } returns
            ApiResult.Success(profile("https://host/uploads/new.jpg"))

        vm.uploadPhoto("image/png") { stream() }
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { profileRepo.me() }
        assertEquals("https://host/uploads/new.jpg", vm.uiState.value.profile?.primaryPhoto)
    }

    @Test
    fun `a refusal leaves the photograph the server still holds`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.uploadPhoto(any(), any()) } returns
            ApiResult.Error(422, "Фото слишком большое. Выберите файл меньшего размера.")

        vm.uploadPhoto("image/jpeg") { stream() }
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("Фото слишком большое. Выберите файл меньшего размера.", vm.uiState.value.uploadError)
        assertEquals("https://host/uploads/old.jpg", vm.uiState.value.profile?.primaryPhoto)
        assertFalse(vm.uiState.value.uploading)
    }

    @Test
    fun `a refusal says nothing about the rest of the tab`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.uploadPhoto(any(), any()) } returns
            ApiResult.Error(422, "Не удалось прочитать фото. Выберите другое.")

        vm.uploadPhoto("image/webp") { stream() }
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The notice belongs to the photograph. The questionnaire percent and the identity rows
        // stayed where the first read put them, because none of them were asked again.
        assertEquals(40, vm.uiState.value.testProgress?.percent)
        assertEquals("Анна", vm.uiState.value.profile?.name)
        assertEquals(null, vm.uiState.value.error)
        assertEquals(null, vm.uiState.value.refreshError)
    }

    @Test
    fun `a file the photo pipeline cannot read is refused before the uplink`() = runTest {
        val vm = loaded()
        var opened = false
        val open: () -> InputStream = { opened = true; stream() }

        vm.uploadPhoto("image/heic", open)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(PHOTO_TYPES_SUPPORTED, vm.uiState.value.uploadError)
        assertFalse("a doomed format must not cost an open or an upload", opened)
        coVerify(exactly = 0) { profileRepo.uploadPhoto(any(), any()) }
    }

    @Test
    fun `a file the system would not label is refused by the same line`() = runTest {
        val vm = loaded()
        var opened = false

        vm.uploadPhoto(null) { opened = true; stream() }
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Guessing a label would send the bytes and let the server refuse them on a guess the app
        // made, so the screen answers with the formats it takes and sends nothing.
        assertEquals(PHOTO_TYPES_SUPPORTED, vm.uiState.value.uploadError)
        assertFalse(opened)
        coVerify(exactly = 0) { profileRepo.uploadPhoto(any(), any()) }
    }

    @Test
    fun `a picture the device would not hand over is named as one and never sent`() = runTest {
        val vm = loaded()

        vm.uploadPhoto("image/jpeg") { throw FileNotFoundException("the picker gave back a uri it would not open") }
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("Не удалось прочитать выбранное фото. Выберите его ещё раз.", vm.uiState.value.uploadError)
        assertFalse(vm.uiState.value.uploading)
        coVerify(exactly = 0) { profileRepo.uploadPhoto(any(), any()) }
    }

    @Test
    fun `a second tap while a picture is on its way sends one picture`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.uploadPhoto(any(), any()) } returns
            ApiResult.Success(profile("https://host/uploads/new.jpg"))
        var opened = 0

        vm.uploadPhoto("image/jpeg") { opened++; stream() }
        assertTrue("the send is in flight", vm.uiState.value.uploading)
        vm.uploadPhoto("image/jpeg") { opened++; stream() }
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(1, opened)
        coVerify(exactly = 1) { profileRepo.uploadPhoto(any(), any()) }
    }

    @Test
    fun `a refused picture leaves the way open for the next one`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.uploadPhoto(any(), any()) } returns
            ApiResult.Error(-1, "Нет подключения к интернету.")

        vm.uploadPhoto("image/jpeg") { stream() }
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Нет подключения к интернету.", vm.uiState.value.uploadError)

        coEvery { profileRepo.uploadPhoto(any(), any()) } returns
            ApiResult.Success(profile("https://host/uploads/new.jpg"))
        vm.uploadPhoto("image/jpeg") { stream() }
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The notice is about one attempt, not a latch: the retry path the screen offers has to
        // actually start a second send rather than sit on the first refusal.
        assertEquals(null, vm.uiState.value.uploadError)
        assertEquals("https://host/uploads/new.jpg", vm.uiState.value.profile?.primaryPhoto)
    }

    @Test
    fun `a successful send clears a refusal it follows`() = runTest {
        val vm = loaded()
        coEvery { profileRepo.uploadPhoto(any(), any()) } returns
            ApiResult.Error(422, "Поддерживаются JPEG, PNG и WEBP.")
        vm.uploadPhoto("image/jpeg") { stream() }
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.uploadError != null)

        coEvery { profileRepo.uploadPhoto(any(), any()) } returns
            ApiResult.Success(profile("https://host/uploads/new.jpg"))
        vm.uploadPhoto("image/jpeg") { stream() }
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(null, vm.uiState.value.uploadError)
    }
}
