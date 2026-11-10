package app.befos.presentation.referrals

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Invite
import app.befos.domain.model.InviteList
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
class ReferralViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val repo: ReferralRepository = mockk()

    private fun invite(
        id: String = "i-1",
        code: String = "abc",
        status: String = "active",
        acceptedAt: String? = null,
        expiresAt: String? = "2026-12-09T23:59:59+00:00",
        createdAt: String? = "2026-11-09T10:00:00+00:00",
    ) = Invite(
        id = id,
        code = code,
        url = "befos://invite/$code",
        status = status,
        expiresAt = expiresAt,
        acceptedAt = acceptedAt,
        createdAt = createdAt,
    )

    @Before
    fun setUp() {
        coEvery { repo.invites() } returns ApiResult.Success(
            InviteList(
                invites = listOf(invite(), invite(id = "i-2", code = "spent", status = "accepted", acceptedAt = "2026-11-01T10:00:00+00:00")),
                acceptedTotal = 1,
            ),
        )
    }

    @Test
    fun `the server list keeps one live door and one spent one apart`() = runTest {
        val vm = ReferralViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("abc", vm.uiState.value.active?.code)
        assertEquals(listOf("spent"), vm.uiState.value.history.map { it.code })
        assertEquals(1, vm.uiState.value.acceptedTotal)
        assertFalse(vm.uiState.value.loading)
    }

    @Test
    fun `creating a link takes the url the server minted, not a local guess`() = runTest {
        val minted = invite(id = "i-3", code = "fresh")
        coEvery { repo.createInvite() } returns ApiResult.Success(minted)
        // The list is read twice: when the screen opens (nothing live yet) and after the create,
        // because a create reloads the server's rows rather than trusting its own echo.
        coEvery { repo.invites() } returnsMany listOf(
            ApiResult.Success(InviteList(emptyList(), 0)),
            ApiResult.Success(InviteList(listOf(minted), 0)),
        )

        val vm = ReferralViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.createInvite()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("fresh", vm.uiState.value.active?.code)
        assertEquals("befos://invite/fresh", vm.uiState.value.active?.url)
        coVerify { repo.createInvite() }
    }

    @Test
    fun `revoking is a two-tap door and clears the code from the list`() = runTest {
        coEvery { repo.revokeInvite("i-1") } returns ApiResult.Success(Unit)
        coEvery { repo.invites() } returns ApiResult.Success(InviteList(listOf(invite()), 0)) andThen
            ApiResult.Success(InviteList(emptyList(), 0))

        val vm = ReferralViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.askRevoke("i-1")
        assertEquals("i-1", vm.uiState.value.confirmRevokeId)

        vm.revoke()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertNull(vm.uiState.value.confirmRevokeId)
        assertTrue(vm.uiState.value.invites.isEmpty())
        coVerify { repo.revokeInvite("i-1") }
    }

    @Test
    fun `the share sheet carries one link and names nobody`() = runTest {
        val vm = ReferralViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        val text = vm.shareText(vm.uiState.value.active!!)

        assertTrue(text.contains("befos://invite/abc"))
        assertFalse(text.contains("@"))
        assertFalse(text.contains("Москва"))
    }

    @Test
    fun `a failed load is a sentence beside an empty list, not a crash`() = runTest {
        coEvery { repo.invites() } returns ApiResult.Error(500, "Сервер не ответил")

        val vm = ReferralViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("Сервер не ответил", vm.uiState.value.error)
        assertTrue(vm.uiState.value.invites.isEmpty())
        assertFalse(vm.uiState.value.loading)
    }
}
