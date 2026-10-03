package app.befos.presentation.auth

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.repository.AuthRepository
import io.mockk.coEvery
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

    @Before
    fun setUp() {
        coEvery { repo.lastEmail() } returns null
    }

    @Test
    fun `fresh device opens on registration`() = runTest {
        val vm = AuthViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.isRegister)
        assertEquals("", vm.uiState.value.email)
    }

    @Test
    fun `remembered email prefills and keeps login mode`() = runTest {
        coEvery { repo.lastEmail() } returns "a@b.co"
        val vm = AuthViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertFalse(vm.uiState.value.isRegister)
        assertEquals("a@b.co", vm.uiState.value.email)
    }

    @Test
    fun `invalid email produces error and no repo call`() = runTest {
        coEvery { repo.login(any(), any()) } returns ApiResult.Success("id")
        val vm = AuthViewModel(repo)
        vm.onEmailChange("not-an-email")
        vm.onPasswordChange("longenough")
        vm.submit()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Введите корректный email.", vm.uiState.value.error)
        assertFalse(vm.uiState.value.success)
    }

    @Test
    fun `short password produces error`() = runTest {
        val vm = AuthViewModel(repo)
        vm.onEmailChange("a@b.co")
        vm.onPasswordChange("123")
        vm.submit()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Пароль должен быть не короче 8 символов.", vm.uiState.value.error)
    }

    @Test
    fun `register password mismatch produces error`() = runTest {
        val vm = AuthViewModel(repo)
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
        val vm = AuthViewModel(repo)
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
        val vm = AuthViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.onPasswordChange("longenough")
        vm.submit()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertFalse(vm.uiState.value.success)
        assertEquals("Неверный пароль", vm.uiState.value.error)
    }
}
