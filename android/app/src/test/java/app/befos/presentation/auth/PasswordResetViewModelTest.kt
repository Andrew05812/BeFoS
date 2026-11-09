package app.befos.presentation.auth

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.data.model.PasswordResetAcceptedDto
import app.befos.domain.repository.AuthRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test

/**
 * What the recovery screens promise, and what they are not allowed to promise.
 *
 * Stage 131 gave the account a way back when its word is lost. These tests hold the client to the
 * same line the backend holds itself to: a request was accepted is not a letter arrived, a refused
 * code leaves the draft alone, and the three questions the server asks about a new word are asked
 * here first so that a mistyped confirmation does not cost a round trip. Each one names the product
 * change that would make it red.
 */
class PasswordResetViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private inner class Fixture {
        val repository: AuthRepository = mockk(relaxed = true)
        val viewModel = PasswordResetViewModel(repository)

        fun scheduler() = mainRule.testDispatcher.scheduler

        fun state() = viewModel.uiState.value
    }

    @Test
    fun `an address that cannot be an address is stopped before the wire`() = runTest {
        val fixture = Fixture()

        fixture.viewModel.onEmailChange("no-at-sign-example.test")
        fixture.viewModel.requestLetter()
        fixture.scheduler().advanceUntilIdle()

        assertEquals("Проверьте адрес почты.", fixture.state().error)
        coVerify(exactly = 0) { fixture.repository.requestPasswordReset(any()) }
    }

    @Test
    fun `an accepted request carries the server's own window, not a number typed in here`() = runTest {
        val fixture = Fixture()
        coEvery { fixture.repository.requestPasswordReset(any()) } returns ApiResult.Success(900)

        fixture.viewModel.onEmailChange("person@example.test")
        fixture.viewModel.requestLetter()
        fixture.scheduler().advanceUntilIdle()

        assertEquals(true, fixture.state().letterSent)
        assertEquals(15, fixture.state().minutes)
        assertNull(fixture.state().error)
    }

    @Test
    fun `a request that was refused says what the backend said`() = runTest {
        val fixture = Fixture()
        coEvery { fixture.repository.requestPasswordReset(any()) } returns
            ApiResult.Error(429, "Слишком много попыток. Подождите минуту.")

        fixture.viewModel.onEmailChange("person@example.test")
        fixture.viewModel.requestLetter()
        fixture.scheduler().advanceUntilIdle()

        assertEquals("Слишком много попыток. Подождите минуту.", fixture.state().error)
        assertEquals(false, fixture.state().letterSent)
        assertEquals(false, fixture.state().busy)
    }

    @Test
    fun `seven characters of a new word are caught before the wire`() = runTest {
        val fixture = Fixture()

        fixture.viewModel.onCodeChange("ABCD-EFGH-JKLM")
        fixture.viewModel.onNewPasswordChange("seventy")
        fixture.viewModel.onConfirmChange("seventy")
        fixture.viewModel.spendCode()
        fixture.scheduler().advanceUntilIdle()

        assertEquals("Пароль должен быть не короче 8 символов.", fixture.state().error)
        coVerify(exactly = 0) { fixture.repository.confirmPasswordReset(any(), any(), any()) }
    }

    @Test
    fun `a confirmation that differs from the new word is refused as one sentence`() = runTest {
        val fixture = Fixture()

        fixture.viewModel.onCodeChange("ABCDEFGHIJKLMNOP")
        fixture.viewModel.onNewPasswordChange("BrandNewWord9")
        fixture.viewModel.onConfirmChange("BrandNewWord8")
        fixture.viewModel.spendCode()
        fixture.scheduler().advanceUntilIdle()

        assertEquals("Пароли не совпадают.", fixture.state().error)
        coVerify(exactly = 0) { fixture.repository.confirmPasswordReset(any(), any(), any()) }
    }

    @Test
    fun `an accepted code empties the draft and carries the person to the login door`() = runTest {
        val fixture = Fixture()
        coEvery { fixture.repository.confirmPasswordReset(any(), any(), any()) } returns
            ApiResult.Success(Unit)

        fixture.viewModel.onCodeChange("ABCD-EFGH-JKLM")
        fixture.viewModel.onNewPasswordChange("BrandNewWord9")
        fixture.viewModel.onConfirmChange("BrandNewWord9")
        fixture.viewModel.spendCode()
        fixture.scheduler().advanceUntilIdle()

        assertEquals(true, fixture.state().done)
        assertEquals("", fixture.state().code)
        assertEquals("", fixture.state().newPassword)
        assertEquals("", fixture.state().passwordConfirm)
        coVerify(exactly = 1) {
            fixture.repository.confirmPasswordReset("ABCD-EFGH-JKLM", "BrandNewWord9", "BrandNewWord9")
        }
    }

    @Test
    fun `a refused code keeps the draft, because the letter still holds that code`() = runTest {
        val fixture = Fixture()
        coEvery { fixture.repository.confirmPasswordReset(any(), any(), any()) } returns
            ApiResult.Error(401, "Код не подошёл. Запросите новое письмо.")

        fixture.viewModel.onCodeChange("ABCD-EFGH-JKLM")
        fixture.viewModel.onNewPasswordChange("BrandNewWord9")
        fixture.viewModel.onConfirmChange("BrandNewWord9")
        fixture.viewModel.spendCode()
        fixture.scheduler().advanceUntilIdle()

        assertEquals("Код не подошёл. Запросите новое письмо.", fixture.state().error)
        assertEquals("ABCD-EFGH-JKLM", fixture.state().code)
        assertEquals(false, fixture.state().done)
    }

    @Test
    fun `a second tap while the code is out is one write`() = runTest {
        val fixture = Fixture()
        coEvery { fixture.repository.confirmPasswordReset(any(), any(), any()) } coAnswers {
            advanceUntilIdle()
            ApiResult.Success(Unit)
        }

        fixture.viewModel.onCodeChange("ABCD-EFGH-JKLM")
        fixture.viewModel.onNewPasswordChange("BrandNewWord9")
        fixture.viewModel.onConfirmChange("BrandNewWord9")
        fixture.viewModel.spendCode()
        fixture.viewModel.spendCode()
        fixture.scheduler().advanceUntilIdle()

        coVerify(exactly = 1) { fixture.repository.confirmPasswordReset(any(), any(), any()) }
    }

    @Test
    fun `typing into a field takes back the sentence the last attempt left`() = runTest {
        val fixture = Fixture()
        coEvery { fixture.repository.confirmPasswordReset(any(), any(), any()) } returns
            ApiResult.Error(401, "Код не подошёл. Запросите новое письмо.")

        fixture.viewModel.onCodeChange("ABCD-EFGH-JKLM")
        fixture.viewModel.onNewPasswordChange("BrandNewWord9")
        fixture.viewModel.onConfirmChange("BrandNewWord8")
        fixture.viewModel.spendCode()
        fixture.scheduler().advanceUntilIdle()
        assertEquals("Пароли не совпадают.", fixture.state().error)

        fixture.viewModel.onConfirmChange("BrandNewWord9")
        assertNull(fixture.state().error)
    }
}
