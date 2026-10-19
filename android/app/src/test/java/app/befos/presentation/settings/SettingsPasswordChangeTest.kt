package app.befos.presentation.settings

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
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
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * The account's own word, replaced from the settings screen.
 *
 * Until this stage the screen offered two endings for a password the person no longer wanted to keep:
 * stay with it, or delete the account. The row below holds the door that opened in between, and what it
 * pins is the shape of the conversation rather than the HTTP call — the wire itself is
 * [app.befos.data.repository.PasswordRotationWritesTest].
 *
 * The two questions the server asks about the new word are asked before the wire, with the same
 * sentences registration uses, so a mistyped confirmation costs no request. A refusal — the old word
 * being wrong most of all — must leave the draft standing: the person has to be able to fix the one
 * field that was wrong without retyping the two that were right, and the session must survive, because
 * the server changed nothing about the account.
 *
 * The success is the interesting half. The account's every refresh token goes away with the old word,
 * including this device's, so the screen cannot stay where it was: the editor closes, the three fields
 * come back empty, and the person is carried to the login door with a sentence saying why.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class SettingsPasswordChangeTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val safety: SafetyRepository = mockk()
    private val auth: AuthRepository = mockk()
    private val profiles: ProfileRepository = mockk()

    private fun open(
        rotation: ApiResult<Unit> = ApiResult.Success(Unit),
        profile: Profile = profile(hidden = false),
    ): SettingsViewModel {
        coEvery { profiles.me() } returns ApiResult.Success(profile)
        coEvery { safety.blockedUsers() } returns ApiResult.Success(emptyList())
        coEvery { auth.sessions() } returns ApiResult.Success(SessionsPage())
        coEvery { auth.changePassword(any(), any(), any()) } returns rotation
        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        return vm
    }

    private fun profile(hidden: Boolean) = Profile(
        userId = "me", name = "Анна", age = 29, city = "Москва", gender = "female",
        about = null, datingGoal = "relationship", photos = emptyList(),
        interests = emptyList(), lifestyle = emptyMap(), ageMin = 25, ageMax = 35,
        genderPreference = emptyList(), isHidden = hidden, isModerator = false,
    )

    private fun typed(vm: SettingsViewModel, old: String, new: String, confirm: String) {
        vm.askPasswordChange()
        vm.onPasswordOldChange(old)
        vm.onPasswordNewChange(new)
        vm.onPasswordConfirmChange(confirm)
    }

    @Test
    fun `the door is closed until the account asks for it`() = runTest {
        val vm = open()

        assertEquals(false, vm.uiState.value.passwordEditorOpen)
        assertEquals("", vm.uiState.value.passwordOld)
        coVerify(exactly = 0) { auth.changePassword(any(), any(), any()) }
    }

    @Test
    fun `an accepted rotation closes the editor, empties the three fields and carries the device to the login door`() = runTest {
        val vm = open()
        typed(vm, "OldWord123", "NewWord123", "NewWord123")

        vm.submitPasswordChange()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.loggedOut)
        assertEquals(false, vm.uiState.value.passwordEditorOpen)
        assertEquals("", vm.uiState.value.passwordOld)
        // A word left in the state after the account has moved on is a secret the screen keeps holding
        // for a session that no longer exists.
        assertEquals("", vm.uiState.value.passwordNew)
        assertEquals("", vm.uiState.value.passwordConfirm)
        assertEquals(false, vm.uiState.value.messageIsError)
        assertTrue(vm.uiState.value.message.orEmpty(), vm.uiState.value.message!!.contains("войти"))
    }

    @Test
    fun `the words go out in the order the server asks them`() = runTest {
        val vm = open()
        typed(vm, "OldWord123", "NewWord123", "NewWord123")

        vm.submitPasswordChange()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { auth.changePassword("OldWord123", "NewWord123", "NewWord123") }
    }

    @Test
    fun `a missing old word is caught before the wire`() = runTest {
        val vm = open()
        typed(vm, "", "NewWord123", "NewWord123")

        vm.submitPasswordChange()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.messageIsError)
        assertEquals("Введите текущий пароль.", vm.uiState.value.message)
        coVerify(exactly = 0) { auth.changePassword(any(), any(), any()) }
        assertEquals(false, vm.uiState.value.loggedOut)
    }

    @Test
    fun `seven characters of a new word are caught before the wire`() = runTest {
        val vm = open()
        typed(vm, "OldWord123", "shortie", "shortie")

        vm.submitPasswordChange()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The same sentence the server's own refusal is translated into, so a person who does spend a
        // round trip — by an older build, or on a screen that forgot the rule — reads one answer.
        assertEquals("Пароль должен быть не короче 8 символов.", vm.uiState.value.message)
        coVerify(exactly = 0) { auth.changePassword(any(), any(), any()) }
    }

    @Test
    fun `a confirmation that differs from the new word is refused as one sentence`() = runTest {
        val vm = open()
        typed(vm, "OldWord123", "NewWord123", "NewWord124")

        vm.submitPasswordChange()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("Пароли не совпадают.", vm.uiState.value.message)
        coVerify(exactly = 0) { auth.changePassword(any(), any(), any()) }
    }

    @Test
    fun `a refusal keeps the draft, the editor and this session`() = runTest {
        val vm = open(ApiResult.Error(401, "Текущий пароль указан неверно."))
        typed(vm, "NotTheirWord1", "NewWord123", "NewWord123")

        vm.submitPasswordChange()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.messageIsError)
        assertEquals("Текущий пароль указан неверно.", vm.uiState.value.message)
        assertEquals(false, vm.uiState.value.loggedOut)
        assertEquals(true, vm.uiState.value.passwordEditorOpen)
        assertEquals("NotTheirWord1", vm.uiState.value.passwordOld)
        assertEquals("NewWord123", vm.uiState.value.passwordNew)
        assertEquals(false, vm.uiState.value.busy)
    }

    @Test
    fun `a second tap while the rotation is out is one write`() = runTest {
        coEvery { profiles.me() } returns ApiResult.Success(profile(hidden = false))
        coEvery { safety.blockedUsers() } returns ApiResult.Success(emptyList())
        coEvery { auth.sessions() } returns ApiResult.Success(SessionsPage())
        val gate = CompletableDeferred<Unit>()
        coEvery { auth.changePassword(any(), any(), any()) } coAnswers {
            gate.await()
            ApiResult.Success(Unit)
        }

        val vm = SettingsViewModel(safety, auth, profiles)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        typed(vm, "OldWord123", "NewWord123", "NewWord123")

        vm.submitPasswordChange()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.submitPasswordChange()

        assertEquals(true, vm.uiState.value.busy)
        coVerify(exactly = 1) { auth.changePassword(any(), any(), any()) }

        gate.complete(Unit)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.loggedOut)
    }

    @Test
    fun `canceling the editor takes the three words back and writes nothing`() = runTest {
        val vm = open()
        typed(vm, "OldWord123", "NewWord123", "NewWord123")

        vm.cancelPasswordChange()

        assertEquals(false, vm.uiState.value.passwordEditorOpen)
        assertEquals("", vm.uiState.value.passwordOld)
        assertEquals("", vm.uiState.value.passwordNew)
        assertEquals("", vm.uiState.value.passwordConfirm)
        coVerify(exactly = 0) { auth.changePassword(any(), any(), any()) }
    }

    @Test
    fun `opening the door again clears the sentence the last attempt left`() = runTest {
        val vm = open(ApiResult.Error(401, "Текущий пароль указан неверно."))
        typed(vm, "NotTheirWord1", "NewWord123", "NewWord123")
        vm.submitPasswordChange()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Текущий пароль указан неверно.", vm.uiState.value.message)

        vm.askPasswordChange()

        assertEquals(null, vm.uiState.value.message)
    }
}
