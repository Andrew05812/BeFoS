package app.befos.presentation.settings

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.DeviceSession
import app.befos.domain.model.Profile
import app.befos.domain.model.SessionsPage
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

/**
 * The account's own devices, read and cut from the settings screen.
 *
 * What is pinned here is the conversation the screen holds, not the HTTP calls — those are
 * [app.befos.data.repository.OwnSessionsReadWritesTest]. Three answers have to stay distinguishable:
 * the list the server gave, a read that never came back, and a list that came back holding nothing. The
 * last one is the account's real state and the second one is not, and a screen that draws «никто не
 * входит» for a failed read would tell a person their account is clean because a request timed out.
 *
 * The writes are the other half. Cutting another device is a fact about that device alone, so the list
 * is re-read from the server's answer rather than edited locally, and the person stays signed in.
 * Cutting this device's row is a fact about the reader, and the screen cannot stay on a section it just
 * invalidated — the account is carried out to the login door. Cutting every row is the door for a lost
 * phone, and it reaches the devices the shown list did not name.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SettingsOwnDevicesTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val safety: SafetyRepository = mockk()
    private val auth: AuthRepository = mockk()
    private val profiles: ProfileRepository = mockk()

    private fun open(
        sessions: ApiResult<SessionsPage> = ApiResult.Success(SessionsPage()),
        profile: Profile = profile(),
    ): SettingsViewModel {
        coEvery { profiles.me() } returns ApiResult.Success(profile)
        coEvery { safety.blockedUsers() } returns ApiResult.Success(emptyList())
        coEvery { auth.sessions() } returns sessions
        coEvery { auth.logout() } returns Unit
        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        return vm
    }

    private fun profile(hidden: Boolean = false) = Profile(
        userId = "me", name = "Анна", age = 29, city = "Москва", gender = "female",
        about = null, datingGoal = "relationship", photos = emptyList(),
        interests = emptyList(), lifestyle = emptyMap(), ageMin = 25, ageMax = 35,
        genderPreference = emptyList(), isHidden = hidden, isModerator = false,
    )

    private fun session(
        id: String,
        device: String? = "Pixel 7, Android 14",
        signedInAt: String = "2026-10-17T09:00:00Z",
        expiresAt: String = "2026-11-16T09:00:00Z",
        current: Boolean = false,
    ) = DeviceSession(id, device, signedInAt, expiresAt, current)

    @Test
    fun `the list the server gives is the list the screen holds`() = runTest {
        val rows = listOf(session("s-1", current = true), session("s-2", "SM-A525F"))
        val vm = open(sessions = ApiResult.Success(SessionsPage(rows, hasMore = false)))

        assertEquals(rows, vm.uiState.value.sessions)
        assertEquals(true, vm.uiState.value.sessionsLoaded)
        assertEquals(false, vm.uiState.value.sessionsUnknown)
        assertEquals(false, vm.uiState.value.sessionsTruncated)
    }

    @Test
    fun `a list that never answered is not read as an account nobody is signed into`() = runTest {
        val vm = open(sessions = ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."))

        // «Аккаунт ни на одном устройстве не входит» and «мы не узнали» are different answers, and the
        // second one is a question about whether a stranger holds this account's session.
        assertEquals(emptyList<DeviceSession>(), vm.uiState.value.sessions)
        assertEquals(false, vm.uiState.value.sessionsLoaded)
        assertEquals(true, vm.uiState.value.sessionsUnknown)
    }

    @Test
    fun `an account with no live session is drawn as one once the server says so`() = runTest {
        val vm = open(sessions = ApiResult.Success(SessionsPage()))

        // The default list is empty too, so the flag is the only thing that separates a clean account
        // from a screen that has not read yet.
        assertEquals(true, vm.uiState.value.sessionsLoaded)
        assertEquals(false, vm.uiState.value.sessionsUnknown)
        assertEquals(0, vm.uiState.value.sessions.size)
    }

    @Test
    fun `a list that ran out says it ran out`() = runTest {
        val rows = (1..50).map { session("s-$it", "Устройство $it") }
        val vm = open(sessions = ApiResult.Success(SessionsPage(rows, hasMore = true)))

        // The server shows fifty rows and names no cursor, so the screen cannot promise the rest is
        // here: the fifty-first row is a device somebody holds and this list did not show.
        assertEquals(50, vm.uiState.value.sessions.size)
        assertEquals(true, vm.uiState.value.sessionsTruncated)
    }

    @Test
    fun `retrying the list reads the devices again without re-reading the profile`() = runTest {
        coEvery { profiles.me() } returns ApiResult.Success(profile())
        coEvery { safety.blockedUsers() } returns ApiResult.Success(emptyList())
        coEvery { auth.sessions() } returnsMany listOf(
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
            ApiResult.Success(SessionsPage(listOf(session("s-1")))),
        )

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.sessionsUnknown)

        vm.loadSessions()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("s-1"), vm.uiState.value.sessions.map { it.id })
        assertEquals(true, vm.uiState.value.sessionsLoaded)
        assertEquals(false, vm.uiState.value.sessionsUnknown)
        coVerify(exactly = 1) { profiles.me() }
        coVerify(exactly = 2) { auth.sessions() }
    }

    @Test
    fun `cutting another device paints the list the server answers next`() = runTest {
        val rows = listOf(session("s-1", current = true), session("s-2", "SM-A525F"))
        val vm = open(sessions = ApiResult.Success(SessionsPage(rows)))
        coEvery { auth.endSession("s-2") } returns ApiResult.Success(Unit)
        coEvery { auth.sessions() } returns ApiResult.Success(SessionsPage(listOf(rows[0])))

        vm.askEndSession(rows[1])
        assertEquals(rows[1], vm.uiState.value.confirmEndSession)
        vm.confirmEndSession()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("s-1"), vm.uiState.value.sessions.map { it.id })
        assertEquals(null, vm.uiState.value.confirmEndSession)
        assertEquals(false, vm.uiState.value.sessionsBusy)
        assertEquals(false, vm.uiState.value.messageIsError)
        // The person stays where they were: the row that went away was not this device's.
        assertEquals(false, vm.uiState.value.loggedOut)
        assertTrue(vm.uiState.value.message.orEmpty(), vm.uiState.value.message!!.contains("SM-A525F"))
        coVerify(exactly = 2) { auth.sessions() }
    }

    @Test
    fun `cutting this device's row carries the account out to the login door`() = runTest {
        val rows = listOf(session("s-1", current = true), session("s-2", "SM-A525F"))
        val vm = open(sessions = ApiResult.Success(SessionsPage(rows)))
        coEvery { auth.endSession("s-1") } returns ApiResult.Success(Unit)

        vm.askEndSession(rows[0])
        vm.confirmEndSession()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The write ended the row this request stood on, so the section the person is reading no longer
        // exists on this device: the screen leaves the account instead of painting a list of a session
        // the server has just revoked.
        coVerify(exactly = 1) { auth.logout() }
        assertEquals(true, vm.uiState.value.loggedOut)
        // No re-read follows this write: the list the section would read back belongs to a session the
        // account no longer holds, and the read would answer with the refusal the login door names.
        coVerify(exactly = 1) { auth.sessions() }
    }

    @Test
    fun `a refused cut leaves the list standing and repeats what the server said`() = runTest {
        val rows = listOf(session("s-2", "SM-A525F"))
        val vm = open(sessions = ApiResult.Success(SessionsPage(rows)))
        coEvery { auth.endSession("s-2") } returns
            ApiResult.Error(404, "Этой сессии уже нет. Обновите список устройств.")

        vm.askEndSession(rows[0])
        vm.confirmEndSession()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(rows, vm.uiState.value.sessions)
        assertEquals(true, vm.uiState.value.messageIsError)
        assertEquals("Этой сессии уже нет. Обновите список устройств.", vm.uiState.value.message)
        assertEquals(false, vm.uiState.value.sessionsBusy)
        assertEquals(false, vm.uiState.value.loggedOut)
    }

    @Test
    fun `a row whose list went stale is still cut by the id the server gave it`() = runTest {
        val rows = listOf(session("s-2", "SM-A525F"))
        val vm = open(sessions = ApiResult.Success(SessionsPage(rows)))
        coEvery { auth.endSession(any()) } returns ApiResult.Success(Unit)
        coEvery { auth.sessions() } returns ApiResult.Success(SessionsPage())

        vm.askEndSession(rows[0])
        vm.confirmEndSession()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Nothing here re-picks the row by its device string or its position: the id the list handed out
        // is the only name the write knows, and a screen that matched on a string could cut a twin.
        coVerify(exactly = 1) { auth.endSession("s-2") }
        assertEquals(true, vm.uiState.value.sessionsLoaded)
        assertEquals(0, vm.uiState.value.sessions.size)
    }

    @Test
    fun `a second cut while the first is out is one write`() = runTest {
        val rows = listOf(session("s-1"), session("s-2", "SM-A525F"))
        val vm = open(sessions = ApiResult.Success(SessionsPage(rows)))

        val gate = CompletableDeferred<Unit>()
        coEvery { auth.endSession("s-1") } coAnswers {
            gate.await()
            ApiResult.Success(Unit)
        }

        vm.askEndSession(rows[0])
        vm.confirmEndSession()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        // The dialog for the second row cannot even be armed while a write is out.
        vm.askEndSession(rows[1])
        assertEquals(null, vm.uiState.value.confirmEndSession)
        vm.confirmEndSession()

        coVerify(exactly = 1) { auth.endSession(any()) }
        assertEquals(true, vm.uiState.value.sessionsBusy)

        gate.complete(Unit)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(false, vm.uiState.value.sessionsBusy)
    }

    @Test
    fun `canceling the dialog ends nobody and asks the server nothing`() = runTest {
        val rows = listOf(session("s-2", "SM-A525F"))
        val vm = open(sessions = ApiResult.Success(SessionsPage(rows)))

        vm.askEndSession(rows[0])
        vm.cancelEndSession()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(null, vm.uiState.value.confirmEndSession)
        assertEquals(rows, vm.uiState.value.sessions)
        coVerify(exactly = 0) { auth.endSession(any()) }
    }

    @Test
    fun `the sweep the dialog was not armed for writes nothing`() = runTest {
        val vm = open()

        vm.confirmEndEverySession()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The gesture that ends every session reaches devices this screen never listed, so it cannot be
        // reachable without the confirmation that says so.
        coVerify(exactly = 0) { auth.endEverySession() }
        assertEquals(false, vm.uiState.value.loggedOut)
    }

    @Test
    fun `ending every session signs this device out with the rest`() = runTest {
        val vm = open(sessions = ApiResult.Success(SessionsPage(listOf(session("s-1", current = true)))))
        coEvery { auth.endEverySession() } returns ApiResult.Success(Unit)

        vm.askEndEverySession()
        assertEquals(true, vm.uiState.value.confirmEndEvery)
        vm.confirmEndEverySession()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(false, vm.uiState.value.confirmEndEvery)
        assertEquals(true, vm.uiState.value.loggedOut)
        assertEquals(false, vm.uiState.value.messageIsError)
        assertTrue(vm.uiState.value.message.orEmpty(), vm.uiState.value.message!!.contains("войти заново"))
        // The answer carries no fresh token pair, so the list cannot be re-read: the session that would
        // read it is among the ones the write ended.
        coVerify(exactly = 1) { auth.sessions() }
    }

    @Test
    fun `a refused sweep leaves the account exactly where it was`() = runTest {
        val rows = listOf(session("s-1", current = true), session("s-2", "SM-A525F"))
        val vm = open(sessions = ApiResult.Success(SessionsPage(rows)))
        coEvery { auth.endEverySession() } returns
            ApiResult.Error(429, "Слишком много запросов. Подождите немного.")

        vm.askEndEverySession()
        vm.confirmEndEverySession()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(rows, vm.uiState.value.sessions)
        assertEquals(true, vm.uiState.value.messageIsError)
        assertEquals("Слишком много запросов. Подождите немного.", vm.uiState.value.message)
        assertEquals(false, vm.uiState.value.loggedOut)
        assertEquals(false, vm.uiState.value.sessionsBusy)
    }

    @Test
    fun `canceling the sweep ends nothing`() = runTest {
        val vm = open(sessions = ApiResult.Success(SessionsPage(listOf(session("s-1")))))

        vm.askEndEverySession()
        vm.cancelEndEverySession()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(false, vm.uiState.value.confirmEndEvery)
        coVerify(exactly = 0) { auth.endEverySession() }
    }

    @Test
    fun `the row's second line names the days the server wrote`() {
        val moscow = ZoneId.of("Europe/Moscow")
        val line = sessionRowWord(session("s-1", current = true), moscow)

        assertEquals("это устройство · вход 17 октября 2026 · до 16 ноября 2026", line)
        assertEquals(
            "вход 17 октября 2026 · до 16 ноября 2026",
            sessionRowWord(session("s-2"), moscow),
        )
    }

    @Test
    fun `the row's second line drops what the server did not say instead of inventing it`() {
        val moscow = ZoneId.of("Europe/Moscow")

        // A timestamp the client cannot read is not a day to print: «вход » with nothing after it reads
        // as a broken row, and an invented date would be a claim about somebody's sign-in.
        assertEquals(
            "это устройство",
            sessionRowWord(session("s-1", signedInAt = "вечер зачёта", expiresAt = "", current = true), moscow),
        )
        assertNull(sessionRowWord(session("s-2", signedInAt = "", expiresAt = ""), moscow))
    }

    @Test
    fun `a device that said nothing about itself is named as one that said nothing`() {
        assertEquals("SM-A525F", deviceWord(session("s-1", "SM-A525F")))
        // Never a brand the client guessed: the string the device sent is the person's own to recognise,
        // and an invented one would point the cut at the wrong phone.
        assertEquals(
            "Устройство, которое ничего о себе не сказало",
            deviceWord(session("s-1", null)),
        )
    }

    @Test
    fun `the message a cut leaves is the row's own name`() = runTest {
        val rows = listOf(session("s-9", null))
        val vm = open(sessions = ApiResult.Success(SessionsPage(rows)))
        coEvery { auth.endSession("s-9") } returns ApiResult.Success(Unit)
        coEvery { auth.sessions() } returns ApiResult.Success(SessionsPage())

        vm.askEndSession(rows[0])
        vm.confirmEndSession()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The sentence that reports the cut uses the same word the row is drawn with, so the person can
        // match the answer to the line they tapped.
        assertTrue(
            vm.uiState.value.message.orEmpty(),
            vm.uiState.value.message!!.contains("Устройство, которое ничего о себе не сказало"),
        )
    }
}
