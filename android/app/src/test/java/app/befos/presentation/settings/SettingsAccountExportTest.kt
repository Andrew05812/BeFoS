package app.befos.presentation.settings

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.AccountExport
import app.befos.domain.model.ExportSection
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
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.time.ZoneId

/**
 * The account taking its own rows out, from the settings screen (stage 121).
 *
 * The screen's whole conversation with this door is pinned here; the bytes and the parsing are
 * [app.befos.data.repository.AccountExportReadTest]. Three answers have to stay distinguishable: a file
 * that arrived, a read that never came back, and a file that arrived holding nothing but the account's
 * own setup. The last one is the person's real state and the second one is not, and a screen that draws
 * «здесь пока только анкета» for a failed read would be telling somebody their life is empty on the
 * strength of a request that timed out.
 *
 * The download is never asked for when the screen opens. A settings page that gathers an account's whole
 * history into memory on every visit would be a privacy cost the person did not agree to and a read the
 * server did not need to answer, so the only thing that starts it is the tap on the row.
 *
 * The two verbs after the read are the other half: the file only leaves the app when the person names a
 * place for it, and discarding it drops the bytes rather than keeping a copy of an account in memory
 * that nobody asked for again.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SettingsAccountExportTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val safety: SafetyRepository = mockk()
    private val auth: AuthRepository = mockk()
    private val profiles: ProfileRepository = mockk()

    private fun open(
        export: ApiResult<AccountExport> = ApiResult.Success(lived()),
    ): SettingsViewModel {
        coEvery { profiles.me() } returns ApiResult.Success(profile())
        coEvery { safety.blockedUsers() } returns ApiResult.Success(emptyList())
        coEvery { auth.sessions() } returns ApiResult.Success(app.befos.domain.model.SessionsPage())
        coEvery { auth.logout() } returns Unit
        // The door is armed, but nothing in `load()` may pull it: the file is only gathered when asked.
        coEvery { profiles.exportAccount() } returns export
        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        return vm
    }

    private fun profile() = Profile(
        userId = "me", name = "Анна", age = 29, city = "Москва", gender = "female",
        about = null, datingGoal = "relationship", photos = emptyList(),
        interests = emptyList(), lifestyle = emptyMap(), ageMin = 25, ageMax = 35,
        genderPreference = emptyList(), isHidden = false, isModerator = false,
    )

    private fun file(
        sections: List<ExportSection>,
        truncated: List<String> = emptyList(),
        generatedAt: String = "2026-10-22T15:04:05.123456+00:00",
    ) = AccountExport(
        bytes = ByteArray(2048),
        fileName = "befos-account-2026-10-22.json",
        generatedAt = generatedAt,
        sections = sections,
        truncated = truncated,
    )

    private fun lived() = file(
        listOf(
            ExportSection("photos", 4),
            ExportSection("questionnaire_answers", 42),
            ExportSection("pairs", 2),
            ExportSection("chats", 300),
            ExportSection("sessions", 1),
        ),
    )

    private fun freshAccountFile() = file(
        listOf(
            ExportSection("photos", 0),
            ExportSection("questionnaire_answers", 0),
            ExportSection("pairs", 0),
            ExportSection("chats", 0),
            ExportSection("sessions", 1),
        ),
    )

    @Test
    fun `opening the screen asks for no file`() = runTest {
        val vm = open()

        // The row is drawn idle and un-read: gathering a whole account is not something a settings page
        // does on the way past.
        coVerify(exactly = 0) { profiles.exportAccount() }
        assertNull(vm.uiState.value.exported)
        assertEquals(false, vm.uiState.value.exportBusy)
        assertEquals(false, vm.uiState.value.exportUnknown)
    }

    @Test
    fun `the file the server hands over is the file the screen holds`() = runTest {
        val vm = open()

        vm.exportAccount()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        val state = vm.uiState.value
        assertEquals(false, state.exportBusy)
        assertEquals(5, state.exported?.sections?.size)
        assertEquals(349, state.exported?.totalRows)
        assertEquals(false, state.exportUnknown)
        assertEquals(false, state.exportSaved)
        assertEquals(false, state.messageIsError)
        assertTrue(state.message.orEmpty(), state.message!!.contains("готов"))
        coVerify(exactly = 1) { profiles.exportAccount() }
    }

    @Test
    fun `a read that never came back is not drawn as an account with nothing in it`() = runTest {
        val vm = open(ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."))

        vm.exportAccount()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        val state = vm.uiState.value
        // «Пока только анкета» and «мы не узнали» are different answers, and the second one is a question
        // about whether the person should trust the door that erases their account.
        assertEquals(null, state.exported)
        assertEquals(true, state.exportUnknown)
        assertEquals(true, state.messageIsError)
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", state.message)
    }

    @Test
    fun `a second tap while the first is out asks the server once`() = runTest {
        val vm = open()
        val gate = CompletableDeferred<ApiResult<AccountExport>>()
        coEvery { profiles.exportAccount() } coAnswers { gate.await() }

        vm.exportAccount()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.exportBusy)
        vm.exportAccount()

        coVerify(exactly = 1) { profiles.exportAccount() }
        gate.complete(ApiResult.Success(lived()))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(false, vm.uiState.value.exportBusy)
    }

    @Test
    fun `a fresh account's file is named as a fresh account's file`() = runTest {
        val vm = open(ApiResult.Success(freshAccountFile()))

        vm.exportAccount()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The file arrived and it is honest about what it holds: the answer is not a failure, and it is
        // not a life either.
        assertEquals(true, vm.uiState.value.exported?.isFreshAccount)
        assertEquals(false, vm.uiState.value.messageIsError)
    }

    @Test
    fun `saving the file names it saved and keeps the card standing`() = runTest {
        val vm = open()
        vm.exportAccount()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.markExportSaved()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        val state = vm.uiState.value
        assertEquals(true, state.exportSaved)
        assertTrue(state.exported != null)
        assertEquals(false, state.messageIsError)
        assertTrue(state.message.orEmpty(), state.message!!.contains("Сохранено"))
    }

    @Test
    fun `discarding the file drops the bytes the person did not keep`() = runTest {
        val vm = open()
        vm.exportAccount()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.discardExport()

        // The whole account was in memory for the length of a decision, and the decision was not to keep
        // it: the card goes, and no read follows — the file is the server's answer, not a section to
        // refresh.
        assertEquals(null, vm.uiState.value.exported)
        assertEquals(false, vm.uiState.value.exportUnknown)
        coVerify(exactly = 1) { profiles.exportAccount() }
    }

    @Test
    fun `asking again replaces the file that was never saved`() = runTest {
        val vm = open()
        vm.exportAccount()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coEvery { profiles.exportAccount() } returns ApiResult.Success(freshAccountFile())
        vm.exportAccount()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.exported?.isFreshAccount)
        assertEquals(false, vm.uiState.value.exportSaved)
        coVerify(exactly = 2) { profiles.exportAccount() }
    }

    @Test
    fun `a file the device refused to write is named as one that is not kept`() = runTest {
        val vm = open()
        vm.exportAccount()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.markExportSaveFailed()

        // The bytes stay in hand: the person chose a place and the write failed, and a screen that
        // dropped the file with the failure would make them gather a whole account again to keep it.
        val state = vm.uiState.value
        assertNotNull(state.exported)
        assertEquals(false, state.exportSaved)
        assertEquals(true, state.messageIsError)
        assertTrue(state.message.orEmpty(), state.message!!.contains("Не удалось сохранить"))
    }

    @Test
    fun `the size the card prints is the size that arrived`() {
        assertEquals("0 Б", exportSizeWord(0))
        assertEquals("512 Б", exportSizeWord(512))
        assertEquals("1 КБ", exportSizeWord(1024))
        // Whole units, rounded down: a card that promised 3 КБ for two and a half of them would be
        // describing a file the person does not hold.
        assertEquals("2 КБ", exportSizeWord(2560))
        assertEquals("1,5 МБ", exportSizeWord(1_572_864))
    }

    @Test
    fun `the sections a cut names are the sections the document named`() {
        val cut = file(listOf(ExportSection("chats", 500), ExportSection("complaints", 3)), truncated = listOf("chats"))

        assertEquals("переписка", exportCutsWord(cut))
        assertEquals(null, exportCutsWord(lived()))
    }

    @Test
    fun `a section the client has no word for keeps the name the document gave it`() {
        assertEquals("переписка", exportSectionWord("chats"))
        assertEquals("ваши касания", exportSectionWord("taps_given"))
        // Never an invention: a key this build has not seen is the server's own name for the section,
        // and the person can find it in the file by that spelling.
        assertEquals("future_rows", exportSectionWord("future_rows"))
    }

    @Test
    fun `the card's day comes off the stamp the server wrote`() {
        val moscow = ZoneId.of("Europe/Moscow")

        assertEquals("22 октября 2026", exportDayWord("2026-10-22T15:04:05.123456+00:00", moscow))
        // A stamp the client cannot read is dropped rather than guessed: the file's own text still
        // carries it, and the screen has no business inventing the day an account was gathered.
        assertEquals(null, exportDayWord("вечер зачёта", moscow))
    }
}
