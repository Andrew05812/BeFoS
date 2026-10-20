package app.befos.presentation.discovery

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.PassedPage
import app.befos.domain.model.PassedUser
import app.befos.domain.repository.DiscoveryRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import java.time.ZoneId

/**
 * The account's own read of the cards it passed, and the release that takes one of those answers back.
 *
 * The wire shape lives in [app.befos.data.repository.PassedUsersReadTest]; what is pinned here is the
 * conversation. Three answers have to stay distinguishable the way the inbox keeps them apart: the list
 * the server gave, a read that never came back, and a list that came back holding nothing. The last is
 * the account's real history and the second is not — a page that drew «вы пока никого не пропускали»
 * over a timeout would tell a person their passes are gone because a request failed.
 *
 * The release is the other half, and it is held to a stricter bargain than the like-back above. The
 * server answers the DELETE with the list that survives, so the page paints that answer instead of
 * subtracting the tapped row: a person the write refused has to stay visible with a working tap, and a
 * row removed on a refusal would be an answer the account never took back, drawn as one it did.
 *
 * The deck is deliberately absent from these checks. A released person cannot rejoin the page of cards
 * already in memory — ranks are assigned once and the release re-queues through the normal refill — so
 * the screen publishes nothing to [app.befos.domain.safety.AnsweredUsers] and says so in its own words.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PassedViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val repo: DiscoveryRepository = mockk()

    private fun row(
        id: String,
        name: String = id,
        age: Int = 31,
        city: String = "Казань",
        passedAt: String = "2026-10-19T06:00:00+00:00",
        photoUrl: String? = "https://host/uploads/$id.png",
    ) = PassedUser(
        userId = id,
        name = name,
        age = age,
        city = city,
        photoUrl = photoUrl,
        passedAt = passedAt,
    )

    private fun open(vararg rows: PassedUser, truncated: Boolean = false): PassedViewModel {
        coEvery { repo.passed() } returns ApiResult.Success(PassedPage(rows.toList(), truncated))
        return PassedViewModel(repo).also { mainRule.testDispatcher.scheduler.advanceUntilIdle() }
    }

    @Test
    fun `the list the server gives is the list the page holds, in the order it gave it`() = runTest {
        val vm = open(row("b"), row("a"))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Newest answer first, as the rows arrive: the page invents no sort of its own.
        assertEquals(listOf("b", "a"), vm.uiState.value.passed.map { it.userId })
        assertEquals(false, vm.uiState.value.truncated)
        assertEquals(false, vm.uiState.value.loading)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `a read that never came back is not drawn as nobody having been passed`() = runTest {
        coEvery { repo.passed() } returns
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")

        val vm = PassedViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // «Вы пока никого не пропускали» is a fact about the account, and a timeout says nothing about it.
        assertEquals(emptyList<PassedUser>(), vm.uiState.value.passed)
        assertEquals(false, vm.uiState.value.isEmpty)
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.error)
    }

    @Test
    fun `an account that has passed nobody is drawn as one once the server says so`() = runTest {
        val vm = open()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.isEmpty)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `a page that ran out says it ran out`() = runTest {
        val rows = (1..50).map { row("u$it") }
        coEvery { repo.passed() } returns ApiResult.Success(PassedPage(rows, truncated = true))
        val vm = PassedViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The server stopped at fifty and names no cursor, so the page cannot promise the rest is here.
        assertEquals(50, vm.uiState.value.passed.size)
        assertEquals(true, vm.uiState.value.truncated)
    }

    @Test
    fun `taking a pass back paints the list the write returned and names who left it`() = runTest {
        val vm = open(row("b", name = "Борис"), row("a", name = "Анна"))
        coEvery { repo.unpass("b") } returns
            ApiResult.Success(PassedPage(listOf(row("a", name = "Анна")), truncated = false))

        vm.release("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("a"), vm.uiState.value.passed.map { it.userId })
        assertEquals(false, vm.uiState.value.busy)
        assertNull(vm.uiState.value.error)
        // The row is gone the moment the write lands, so the notice has to carry the name out of it: a
        // message pointing at nobody leaves the reader wondering whether the tap did anything.
        assertEquals("Борис", vm.uiState.value.released)
        coVerify(exactly = 1) { repo.passed() }
    }

    @Test
    fun `a refused release keeps the person on the page and calls the return unrecorded`() = runTest {
        val vm = open(row("b"))
        coEvery { repo.unpass("b") } returns
            ApiResult.Error(404, "Вы этого человека не пропускали. Обновите список.")

        vm.release("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The row is the only evidence the account has that it passed this person; hiding it on a write
        // the server refused would erase an answer that is still written.
        assertEquals(listOf("b"), vm.uiState.value.passed.map { it.userId })
        assertEquals(false, vm.uiState.value.busy)
        assertNull(vm.uiState.value.released)
        assertTrue(vm.uiState.value.error.orEmpty(), vm.uiState.value.error!!.contains("Возврат не записан"))
        assertTrue(vm.uiState.value.error.orEmpty(), vm.uiState.value.error!!.contains("не пропускали"))
    }

    @Test
    fun `a release whose server page still holds the person keeps the row visible`() = runTest {
        val vm = open(row("b"), row("a"))
        // The page the write returns is the server's answer even when it surprises this screen: a list
        // that still names the person is drawn as one that still names them.
        coEvery { repo.unpass("b") } returns
            ApiResult.Success(PassedPage(listOf(row("b"), row("a")), truncated = false))

        vm.release("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("b", "a"), vm.uiState.value.passed.map { it.userId })
        assertEquals("b", vm.uiState.value.released)
    }

    @Test
    fun `the notice once read stays read`() = runTest {
        val vm = open(row("b", name = "Борис"))
        coEvery { repo.unpass("b") } returns ApiResult.Success(PassedPage(emptyList(), truncated = false))

        vm.release("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.dismissReleased()

        assertNull(vm.uiState.value.released)
        assertFalse(vm.uiState.value.loading)
    }

    @Test
    fun `a second release while the first is out is one write`() = runTest {
        val vm = open(row("b"), row("a"))
        val gate = CompletableDeferred<Unit>()
        coEvery { repo.unpass("b") } coAnswers {
            gate.await()
            ApiResult.Success(PassedPage(listOf(row("a")), truncated = false))
        }

        vm.release("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.release("a")

        coVerify(exactly = 1) { repo.unpass(any()) }
        assertEquals(true, vm.uiState.value.busy)

        gate.complete(Unit)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(false, vm.uiState.value.busy)
        coVerify(exactly = 0) { repo.unpass("a") }
    }

    @Test
    fun `refreshing the page reads the list again and paints what comes back`() = runTest {
        coEvery { repo.passed() } returnsMany listOf(
            ApiResult.Success(PassedPage(listOf(row("b")), truncated = false)),
            ApiResult.Success(PassedPage(listOf(row("c"), row("b")), truncated = false)),
        )
        val vm = PassedViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("b"), vm.uiState.value.passed.map { it.userId })

        // The page does not watch the list on its own: an answer taken back elsewhere reaches this
        // screen through the read the truncation notice offers, the way the inbox does.
        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("c", "b"), vm.uiState.value.passed.map { it.userId })
        coVerify(exactly = 2) { repo.passed() }
    }

    @Test
    fun `the row's second line names the day the server wrote`() {
        val moscow = ZoneId.of("Europe/Moscow")

        assertEquals(
            "31 · Казань · 19 октября 2026",
            passedRowWord(row("b", passedAt = "2026-10-19T06:00:00+00:00"), moscow),
        )
        // The day belongs to the reader, not to UTC: a card swiped past late in the evening of one
        // calendar day is already the next morning for a person three hours ahead.
        assertEquals(
            "31 · Казань · 20 октября 2026",
            passedRowWord(row("b", passedAt = "2026-10-19T23:30:00+00:00"), moscow),
        )
    }

    @Test
    fun `the row's second line drops the day the server did not write`() {
        val moscow = ZoneId.of("Europe/Moscow")

        // An unreadable instant is not a day to print, and inventing one would date somebody's answer.
        assertEquals("31 · Казань", passedRowWord(row("b", passedAt = ""), moscow))
        assertEquals("31 · Казань", passedRowWord(row("b", passedAt = "вечер зачёта"), moscow))
    }

    @Test
    fun `the door into the page is named by the one word the app uses for it`() {
        // The deck's header and the profile tab both lead here, and a second label for the same route
        // would be a second door the person has to learn.
        assertEquals("Кого вы пропускали", app.befos.presentation.common.passedEntryWord())
    }
}
