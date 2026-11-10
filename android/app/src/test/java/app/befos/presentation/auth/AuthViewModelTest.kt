package app.befos.presentation.auth

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.ConsentDocument
import app.befos.domain.model.InvitePreview
import app.befos.domain.repository.AuthRepository
import app.befos.domain.repository.ReferralRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AuthViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val repo: AuthRepository = mockk()
    // Only offerInvitation touches it; the cases that do not carry a link never stub it.
    private val referrals: ReferralRepository = mockk()

    private val document = ConsentDocument(
        version = "7",
        effectiveDate = "2026-11-09",
        text = "Текст согласия, который показывает сервер.",
    )

    @Before
    fun setUp() {
        coEvery { repo.lastEmail() } returns null
        coEvery { repo.consent() } returns ApiResult.Success(document)
    }

    @Test
    fun `fresh device opens on registration`() = runTest {
        val vm = AuthViewModel(repo, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.isRegister)
        assertEquals("", vm.uiState.value.email)
    }

    @Test
    fun `remembered email prefills and keeps login mode`() = runTest {
        coEvery { repo.lastEmail() } returns "a@b.co"
        val vm = AuthViewModel(repo, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertFalse(vm.uiState.value.isRegister)
        assertEquals("a@b.co", vm.uiState.value.email)
    }

    @Test
    fun `invalid email produces error and no repo call`() = runTest {
        coEvery { repo.login(any(), any()) } returns ApiResult.Success("id")
        val vm = AuthViewModel(repo, referrals)
        vm.onEmailChange("not-an-email")
        vm.onPasswordChange("longenough")
        vm.submit()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Введите корректный email.", vm.uiState.value.error)
        assertFalse(vm.uiState.value.success)
    }

    @Test
    fun `short password produces error`() = runTest {
        val vm = AuthViewModel(repo, referrals)
        vm.onEmailChange("a@b.co")
        vm.onPasswordChange("123")
        vm.submit()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Пароль должен быть не короче 8 символов.", vm.uiState.value.error)
    }

    @Test
    fun `register password mismatch produces error`() = runTest {
        val vm = AuthViewModel(repo, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onEmailChange("a@b.co")
        vm.onPasswordChange("longenough")
        vm.onPasswordConfirmChange("different")
        vm.submit()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Пароли не совпадают.", vm.uiState.value.error)
    }

    @Test
    fun `successful login sets success and clears error`() = runTest {
        coEvery { repo.lastEmail() } returns "a@b.co"
        coEvery { repo.login("a@b.co", "longenough") } returns ApiResult.Success("user-1")
        val vm = AuthViewModel(repo, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onPasswordChange("longenough")
        vm.submit()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.success)
        assertNull(vm.uiState.value.error)
        assertFalse(vm.uiState.value.loading)
    }

    @Test
    fun `login failure surfaces backend message`() = runTest {
        coEvery { repo.lastEmail() } returns "a@b.co"
        coEvery { repo.login(any(), any()) } returns ApiResult.Error(401, "Неверный пароль")
        val vm = AuthViewModel(repo, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onPasswordChange("longenough")
        vm.submit()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertFalse(vm.uiState.value.success)
        assertEquals("Неверный пароль", vm.uiState.value.error)
    }

    @Test
    fun `the register branch puts the server's text in front of the person`() = runTest {
        val vm = AuthViewModel(repo, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.isRegister)
        assertEquals("7", vm.uiState.value.consent?.version)
        assertFalse(vm.uiState.value.consentChecked)
        // The login branch asks nobody to accept a document they are not making an account under.
        vm.toggleMode()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertFalse(vm.uiState.value.isRegister)
    }

    @Test
    fun `registration without the checked text calls no door and says why`() = runTest {
        val vm = AuthViewModel(repo, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onEmailChange("new@befos.app")
        vm.onPasswordChange("longenough")
        vm.onPasswordConfirmChange("longenough")
        vm.submit()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("Прочитайте и примите текст согласия.", vm.uiState.value.error)
        assertFalse(vm.uiState.value.success)
        coVerify(exactly = 0) { repo.register(any(), any(), any(), any()) }
    }

    @Test
    fun `registration carries the version of the text the screen showed`() = runTest {
        coEvery { repo.register("new@befos.app", "longenough", "7", null) } returns
            ApiResult.Success("u-1")
        val vm = AuthViewModel(repo, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onEmailChange("new@befos.app")
        vm.onPasswordChange("longenough")
        vm.onPasswordConfirmChange("longenough")
        vm.onConsentChecked(true)
        vm.submit()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.success)
        coVerify { repo.register("new@befos.app", "longenough", "7", null) }
    }

    @Test
    fun `an invitation opens registration and is kept as a bearer code`() = runTest {
        coEvery { referrals.previewInvite("a-door") } returns ApiResult.Success(
            InvitePreview(valid = true, expiresAt = "2026-12-09T23:59:59+00:00"),
        )
        val vm = AuthViewModel(repo, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.offerInvitation("a-door")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        val invitation = vm.uiState.value.invitation
        assertTrue(vm.uiState.value.isRegister)
        assertEquals("a-door", invitation?.code)
        assertEquals(true, invitation?.valid)
        assertFalse(invitation?.checking ?: true)
        assertEquals("2026-12-09T23:59:59+00:00", invitation?.expiresAt)
    }

    @Test
    fun `a spent invitation still leaves a usable form`() = runTest {
        coEvery { referrals.previewInvite("spent") } returns ApiResult.Success(
            InvitePreview(valid = false, expiresAt = null),
        )
        val vm = AuthViewModel(repo, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.offerInvitation("spent")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.isRegister)
        assertEquals(false, vm.uiState.value.invitation?.valid)
        // The preview names no person and prints no code of its own; the code stays in the state
        // only to be sent once, with the register call.
        assertEquals("spent", vm.uiState.value.invitation?.code)
    }

    @Test
    fun `a failed preview does not block registration and still sends the code`() = runTest {
        coEvery { referrals.previewInvite("a-door") } returns ApiResult.Error(0, "Нет соединения")
        coEvery { repo.register("new@befos.app", "longenough", "7", "a-door") } returns
            ApiResult.Success("u-1")
        val vm = AuthViewModel(repo, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.offerInvitation("a-door")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onEmailChange("new@befos.app")
        vm.onPasswordChange("longenough")
        vm.onPasswordConfirmChange("longenough")
        vm.onConsentChecked(true)
        vm.submit()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertNull(vm.uiState.value.invitation?.valid)
        assertTrue(vm.uiState.value.success)
        coVerify { repo.register("new@befos.app", "longenough", "7", "a-door") }
    }

    @Test
    fun `declining or walking to login drops the invitation`() = runTest {
        coEvery { referrals.previewInvite("a-door") } returns ApiResult.Success(InvitePreview(true, null))
        val vm = AuthViewModel(repo, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.offerInvitation("a-door")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.declineInvitation()
        assertNull(vm.uiState.value.invitation)
        assertTrue(vm.uiState.value.isRegister)

        vm.offerInvitation("a-door")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.toggleMode()
        assertNull(vm.uiState.value.invitation)
    }
}
