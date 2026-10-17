package app.befos.presentation.settings

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.BlockedUser
import app.befos.domain.model.Profile
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.SafetyRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.time.ZoneId

@OptIn(ExperimentalCoroutinesApi::class)
class SettingsViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val safety: SafetyRepository = mockk()
    private val auth: AuthRepository = mockk()
    private val profiles: ProfileRepository = mockk()

    private fun profile(hidden: Boolean) = Profile(
        userId = "me", name = "Анна", age = 29, city = "Москва", gender = "female",
        about = null, datingGoal = "relationship", photos = emptyList(),
        interests = emptyList(), lifestyle = emptyMap(), ageMin = 25, ageMax = 35,
        genderPreference = emptyList(), isHidden = hidden,
    )

    private fun blocked(id: String, name: String) = BlockedUser(
        userId = id,
        name = name,
        age = 30,
        city = "Москва",
        photoUrl = null,
        blockedAt = "2026-10-17T09:00:00Z",
    )

    /** The list read answers with nobody blocked, unless a test says otherwise. */
    private fun blocksAreIdle() {
        coEvery { safety.blockedUsers() } returns ApiResult.Success(emptyList())
    }

    @Test
    fun `a visibility check that never answered says the switch is unverified`() = runTest {
        blocksAreIdle()
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
        blocksAreIdle()
        coEvery { profiles.me() } returns ApiResult.Success(profile(hidden = true))

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.hidden)
        assertEquals(false, vm.uiState.value.visibilityUnknown)
    }

    @Test
    fun `an answer the server confirms settles the warning`() = runTest {
        blocksAreIdle()
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
        coEvery { safety.blockedUsers() } returns ApiResult.Success(emptyList())
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

    @Test
    fun `a block list that never answered is not read as a profile that blocks nobody`() = runTest {
        blocksAreIdle()
        coEvery { profiles.me() } returns ApiResult.Success(profile(hidden = false))
        coEvery { safety.blockedUsers() } returns
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // «Вы пока никого не блокировали» and «мы не узнали» have to stay different answers: the
        // second one is a question about somebody's privacy, and an empty list draws it as closed.
        assertEquals(emptyList<BlockedUser>(), vm.uiState.value.blocked)
        assertEquals(false, vm.uiState.value.blocksLoaded)
        assertEquals(true, vm.uiState.value.blocksUnknown)
    }

    @Test
    fun `the list the server gives is the list the screen holds`() = runTest {
        blocksAreIdle()
        coEvery { profiles.me() } returns ApiResult.Success(profile(hidden = false))
        val rows = listOf(blocked("u-nina", "Нина"), blocked("u-oleg", "Олег"))
        coEvery { safety.blockedUsers() } returns ApiResult.Success(rows)

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(rows, vm.uiState.value.blocked)
        assertEquals(true, vm.uiState.value.blocksLoaded)
        assertEquals(false, vm.uiState.value.blocksUnknown)
    }

    @Test
    fun `releasing a block paints the list the server answered`() = runTest {
        blocksAreIdle()
        coEvery { profiles.me() } returns ApiResult.Success(profile(hidden = false))
        val rows = listOf(blocked("u-nina", "Нина"), blocked("u-oleg", "Олег"))
        coEvery { safety.blockedUsers() } returns ApiResult.Success(rows)
        // The server's answer holds only the row that survived the write — and it is the answer, not
        // the local list minus the tap, that the screen then draws.
        coEvery { safety.unblock("u-nina") } returns ApiResult.Success(listOf(rows[1]))

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.askUnblock(rows[0])
        assertEquals(rows[0], vm.uiState.value.confirmUnblock)
        vm.confirmUnblock()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf(rows[1]), vm.uiState.value.blocked)
        assertEquals(null, vm.uiState.value.confirmUnblock)
        assertEquals(false, vm.uiState.value.blocksBusy)
        assertEquals(false, vm.uiState.value.messageIsError)
        assertTrue(vm.uiState.value.message.orEmpty(), vm.uiState.value.message!!.contains("Нина"))
    }

    @Test
    fun `a refused release leaves the list standing and repeats what the server said`() = runTest {
        blocksAreIdle()
        coEvery { profiles.me() } returns ApiResult.Success(profile(hidden = false))
        val rows = listOf(blocked("u-nina", "Нина"))
        coEvery { safety.blockedUsers() } returns ApiResult.Success(rows)
        coEvery { safety.unblock("u-nina") } returns ApiResult.Error(404, "Вы этого человека не блокировали. Обновите список.")

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.askUnblock(rows[0])
        vm.confirmUnblock()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(rows, vm.uiState.value.blocked)
        assertEquals(true, vm.uiState.value.messageIsError)
        assertEquals("Вы этого человека не блокировали. Обновите список.", vm.uiState.value.message)
        assertEquals(false, vm.uiState.value.blocksBusy)
    }

    @Test
    fun `a second release tap while the first is out is one write`() = runTest {
        blocksAreIdle()
        coEvery { profiles.me() } returns ApiResult.Success(profile(hidden = false))
        val rows = listOf(blocked("u-nina", "Нина"), blocked("u-oleg", "Олег"))
        coEvery { safety.blockedUsers() } returns ApiResult.Success(rows)

        // The first write is held open, so a second tap has to be dropped rather than queued behind it:
        // the row the person is told about is one answer, not a blend of two, and the screen disables
        // the taps for exactly this — the ViewModel is what keeps the promise when a tap slips through.
        val gate = CompletableDeferred<Unit>()
        coEvery { safety.unblock("u-nina") } coAnswers {
            gate.await()
            ApiResult.Success(listOf(rows[1]))
        }

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.askUnblock(rows[0])
        vm.confirmUnblock()
        // The write is put on the wire here and stops at the gate, so the taps below land on a screen
        // that is genuinely waiting for an answer rather than on a coroutine that has not started yet.
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.askUnblock(rows[1])
        vm.confirmUnblock()

        coVerify(exactly = 1) { safety.unblock(any()) }
        assertEquals(null, vm.uiState.value.confirmUnblock)
        assertEquals(true, vm.uiState.value.blocksBusy)

        gate.complete(Unit)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf(rows[1]), vm.uiState.value.blocked)
        assertEquals(false, vm.uiState.value.blocksBusy)
    }

    @Test
    fun `canceling the dialog releases nobody and asks the server nothing`() = runTest {
        blocksAreIdle()
        coEvery { profiles.me() } returns ApiResult.Success(profile(hidden = false))
        val rows = listOf(blocked("u-nina", "Нина"))
        coEvery { safety.blockedUsers() } returns ApiResult.Success(rows)

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.askUnblock(rows[0])
        vm.cancelUnblock()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(null, vm.uiState.value.confirmUnblock)
        assertEquals(rows, vm.uiState.value.blocked)
        coVerify(exactly = 0) { safety.unblock(any()) }
    }

    @Test
    fun `retrying the list does not re-read the profile`() = runTest {
        coEvery { safety.blockedUsers() } returnsMany listOf(
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
            ApiResult.Success(listOf(blocked("u-nina", "Нина"))),
        )
        coEvery { profiles.me() } returns ApiResult.Success(profile(hidden = false))

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.blocksUnknown)

        vm.loadBlocks()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("u-nina"), vm.uiState.value.blocked.map { it.userId })
        assertEquals(false, vm.uiState.value.blocksUnknown)
        coVerify(exactly = 1) { profiles.me() }
        coVerify(exactly = 2) { safety.blockedUsers() }
    }

    @Test
    fun `the row names the day the server wrote and drops it when the text is not a day`() {
        val moscow = ZoneId.of("Europe/Moscow")
        val line = blockedRowWord(blocked("u-nina", "Нина"), moscow)

        assertEquals("30 · Москва · 17 октября 2026", line)
        assertEquals(
            "30 · Москва",
            blockedRowWord(blocked("u-nina", "Нина").copy(blockedAt = "вечер зачёта"), moscow),
        )
        assertEquals("30 · Москва", blockedRowWord(blocked("u-nina", "Нина").copy(blockedAt = ""), moscow))
    }
}
