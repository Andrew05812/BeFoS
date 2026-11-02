package app.befos.presentation.common

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.core.network.BROKEN_PAGE_LINK_CODE
import app.befos.domain.model.IncomingLike
import app.befos.domain.model.LikedMePage
import app.befos.domain.model.MatchSummary
import app.befos.domain.model.MatchesPage
import app.befos.domain.model.PassedPage
import app.befos.domain.model.PassedUser
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.repository.MatchRepository
import app.befos.domain.safety.AnsweredUsers
import app.befos.presentation.discovery.LikedMeViewModel
import app.befos.presentation.discovery.PassedViewModel
import app.befos.presentation.matches.MatchesViewModel
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

/**
 * The walk every paged list of stage 126 goes on: the page that opens, the page behind its link, and
 * what happens when that page does not come.
 *
 * Three screens read three doors, and the branch that decides what the tail of each one says lives in
 * one place ([pageTail]) — so the table is pinned once, and the three screens are pinned on the two
 * things only a screen can get wrong: whether it asks twice for the same page, and whether it knows
 * the difference between a page that did not arrive and a link the server refuses to open. The second
 * difference is the one that decides whether a person ever sees the rows behind a stale frontier: a
 * screen that repeats a dead link never reaches them, and a screen that re-reads the newest page does.
 *
 * The row shapes are the domain's, so nothing here depends on the wire — that half is
 * [app.befos.data.repository], and the seal on the link is the server's
 * (`test_a_page_link_is_issued_by_the_server_and_not_by_the_reader`).
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PagedListWalkTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val inboxRepo: DiscoveryRepository = mockk()
    private val passRepo: DiscoveryRepository = mockk()
    private val matchRepo: MatchRepository = mockk()
    private val answered: AnsweredUsers = mockk(relaxed = true)

    private fun liked(id: String) = IncomingLike(
        userId = id, name = "Вера", age = 30, city = "Казань", photoUrl = null,
        compatibility = 80, likedAt = "2026-11-01T06:00:00+00:00",
    )

    private fun passed(id: String) = PassedUser(
        userId = id, name = "Пётр", age = 33, city = "Москва", photoUrl = null,
        passedAt = "2026-11-01T06:00:00+00:00",
    )

    private fun pair(id: String) = MatchSummary(
        matchId = id, userId = "u-$id", name = "Аня", age = 27, city = "Тверь", photoUrl = null,
        compatibility = 74, lastMessage = null, lastMessageAt = null, unread = 0,
    )

    private fun fail(code: String = "", text: String = "Нет соединения.") = ApiResult.Error(422, text, code)

    private fun idle() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    // ---------------------------------------------------------------- the shared tail

    @Test
    fun `the tail says what the walk holds and nothing more`() {
        val held = PageWalk(
            loadingMore = false, moreError = null, moreErrorCode = "",
            truncated = true, nextCursor = "c1", pages = 2,
        )
        assertEquals("a page is on the wire, and the rows above it stay", PageTail.Loading,
            pageTail(held.copy(loadingMore = true)))
        assertEquals("the door refused the link itself", PageTail.LinkRefused,
            pageTail(held.copy(moreError = "Ссылка сломана.", moreErrorCode = BROKEN_PAGE_LINK_CODE)))
        assertEquals("the page did not arrive and its key is still held", PageTail.PageRefused,
            pageTail(held.copy(moreError = "Сервер недоступен.")))
        assertEquals("nothing is wrong, and there is more to read", PageTail.MoreAvailable, pageTail(held))
        assertEquals(
            "a reload that failed threw the key away: the walk can only be picked up by reading again",
            PageTail.WaitingForReread, pageTail(held.copy(nextCursor = null)),
        )
        assertEquals(
            "the last answer named no rows behind these",
            PageTail.End, pageTail(held.copy(truncated = false, nextCursor = null)),
        )
        assertEquals(
            "one page, nothing behind it — the list itself says all there is",
            PageTail.Nothing, pageTail(held.copy(truncated = false, nextCursor = null, pages = 1)),
        )
    }

    @Test
    fun `the end sentence never appears over a list the reader has not finished`() {
        // `truncated` is the server's word that more rows stand behind the page. An absent link alone
        // is not the end of the walk: it is a key this screen lost, and telling a person they have read
        // everything is the one sentence that cannot be repaired from the screen.
        val lost = PageWalk(
            loadingMore = false, moreError = null, moreErrorCode = "",
            truncated = true, nextCursor = null, pages = 1,
        )
        assertEquals(PageTail.WaitingForReread, pageTail(lost))
    }

    // ---------------------------------------------------------------- the inbox

    @Test
    fun `the inbox opens on the newest page and holds the key to the rest`() = runTest {
        coEvery { inboxRepo.likedMe(null) } returns ApiResult.Success(
            LikedMePage(listOf(liked("a"), liked("b")), truncated = true, nextCursor = "c2")
        )
        val vm = LikedMeViewModel(inboxRepo, answered)
        idle()

        assertEquals(listOf("a", "b"), vm.uiState.value.likes.map { it.userId })
        assertEquals("c2", vm.uiState.value.nextCursor)
        assertEquals(1, vm.uiState.value.pages)
        assertTrue(vm.uiState.value.truncated)
    }

    @Test
    fun `a page of the inbox arrives behind the link the previous page handed out`() = runTest {
        coEvery { inboxRepo.likedMe(null) } returns ApiResult.Success(
            LikedMePage(listOf(liked("a")), truncated = true, nextCursor = "c2")
        )
        coEvery { inboxRepo.likedMe("c2") } returns ApiResult.Success(
            LikedMePage(listOf(liked("b"), liked("c")), truncated = false, nextCursor = null)
        )
        val vm = LikedMeViewModel(inboxRepo, answered)
        idle()

        vm.loadMore()
        idle()

        assertEquals(listOf("a", "b", "c"), vm.uiState.value.likes.map { it.userId })
        assertEquals(2, vm.uiState.value.pages)
        assertNull("the server said nothing stands beyond these rows", vm.uiState.value.nextCursor)
        assertFalse("the walk is over, so no verb asks for another page", vm.uiState.value.canLoadMore)
        assertFalse(vm.uiState.value.truncated)
    }

    @Test
    fun `a person the inbox names twice is listed once`() = runTest {
        coEvery { inboxRepo.likedMe(null) } returns ApiResult.Success(
            LikedMePage(listOf(liked("a")), truncated = true, nextCursor = "c2")
        )
        // A tap withdrawn and given again between two pages writes a fresh row for the same person, and
        // the keyset cannot know the reader has already met them.
        coEvery { inboxRepo.likedMe("c2") } returns ApiResult.Success(
            LikedMePage(listOf(liked("a"), liked("b")), truncated = false, nextCursor = null)
        )
        val vm = LikedMeViewModel(inboxRepo, answered)
        idle()
        vm.loadMore()
        idle()

        assertEquals(listOf("a", "b"), vm.uiState.value.likes.map { it.userId })
        assertEquals(2, vm.uiState.value.pages)
    }

    @Test
    fun `reaching the end twice while a page is on the wire asks the door once`() = runTest {
        val gate = CompletableDeferred<ApiResult<LikedMePage>>()
        coEvery { inboxRepo.likedMe(null) } returns ApiResult.Success(
            LikedMePage(listOf(liked("a")), truncated = true, nextCursor = "c2")
        )
        coEvery { inboxRepo.likedMe("c2") } coAnswers { gate.await() }
        val vm = LikedMeViewModel(inboxRepo, answered)
        idle()

        vm.loadMore()
        vm.loadMore()
        vm.loadMore()
        assertFalse("a page is already out", vm.uiState.value.canLoadMore)
        gate.complete(ApiResult.Success(LikedMePage(listOf(liked("b")), truncated = false, nextCursor = null)))
        idle()

        coVerify(exactly = 1) { inboxRepo.likedMe("c2") }
        assertEquals(listOf("a", "b"), vm.uiState.value.likes.map { it.userId })
    }

    @Test
    fun `a refused page closes the automatic walk and keeps the rows above it`() = runTest {
        coEvery { inboxRepo.likedMe(null) } returns ApiResult.Success(
            LikedMePage(listOf(liked("a")), truncated = true, nextCursor = "c2")
        )
        coEvery { inboxRepo.likedMe("c2") } returns fail(text = "Сервер недоступен.")
        val vm = LikedMeViewModel(inboxRepo, answered)
        idle()
        vm.loadMore()
        idle()

        assertEquals("Сервер недоступен.", vm.uiState.value.moreError)
        assertEquals(
            "the notice carries the words; the walk does not knock again on its own",
            false, vm.uiState.value.canLoadMore,
        )
        assertEquals(listOf("a"), vm.uiState.value.likes.map { it.userId })
        assertEquals("the key survives a page that merely failed to arrive", "c2", vm.uiState.value.nextCursor)
        coVerify(exactly = 1) { inboxRepo.likedMe("c2") }
    }

    @Test
    fun `a link the server refuses is dropped and the newest page is read again`() = runTest {
        coEvery { inboxRepo.likedMe(null) } returnsMany listOf(
            ApiResult.Success(LikedMePage(listOf(liked("a")), truncated = true, nextCursor = "c2")),
            ApiResult.Success(LikedMePage(listOf(liked("x"), liked("y")), truncated = false, nextCursor = null)),
        )
        coEvery { inboxRepo.likedMe("c2") } returns
            fail(code = BROKEN_PAGE_LINK_CODE, text = "Продолжить список не удалось.")
        val vm = LikedMeViewModel(inboxRepo, answered)
        idle()
        vm.loadMore()
        idle()
        assertEquals(PageTail.LinkRefused, pageTail(vm.uiState.value.walk()))

        vm.retryMore()
        idle()

        coVerify(exactly = 2) { inboxRepo.likedMe(null) }
        assertEquals(listOf("x", "y"), vm.uiState.value.likes.map { it.userId })
        assertEquals(1, vm.uiState.value.pages)
        assertNull(vm.uiState.value.moreError)
    }

    @Test
    fun `a page that only failed to arrive is asked for again by the same key`() = runTest {
        coEvery { inboxRepo.likedMe(null) } returns ApiResult.Success(
            LikedMePage(listOf(liked("a")), truncated = true, nextCursor = "c2")
        )
        coEvery { inboxRepo.likedMe("c2") } returnsMany listOf(
            fail(text = "Сервер недоступен."),
            ApiResult.Success(LikedMePage(listOf(liked("b")), truncated = false, nextCursor = null)),
        )
        val vm = LikedMeViewModel(inboxRepo, answered)
        idle()
        vm.loadMore()
        idle()

        vm.retryMore()
        idle()

        coVerify(exactly = 2) { inboxRepo.likedMe("c2") }
        assertEquals(listOf("a", "b"), vm.uiState.value.likes.map { it.userId })
    }

    @Test
    fun `a reload that fails leaves the rows and the key behind, and the tail says so`() = runTest {
        coEvery { inboxRepo.likedMe(null) } returnsMany listOf(
            ApiResult.Success(LikedMePage(listOf(liked("a")), truncated = true, nextCursor = "c2")),
            fail(text = "Сервер недоступен."),
        )
        val vm = LikedMeViewModel(inboxRepo, answered)
        idle()
        vm.load()
        idle()

        assertEquals(listOf("a"), vm.uiState.value.likes.map { it.userId })
        assertNull("a link into a list this read failed to re-open is not held on", vm.uiState.value.nextCursor)
        assertEquals("Сервер недоступен.", vm.uiState.value.error)
    }

    // ---------------------------------------------------------------- the pass list

    @Test
    fun `the pass list walks to its older rows and a release deeper down keeps the walk`() = runTest {
        coEvery { passRepo.passed(null) } returns ApiResult.Success(
            PassedPage(listOf(passed("a")), truncated = true, nextCursor = "c2")
        )
        coEvery { passRepo.passed("c2") } returns ApiResult.Success(
            PassedPage(listOf(passed("b")), truncated = true, nextCursor = "c3")
        )
        // The door answers a release with the page that stands after the write — the newest one.
        coEvery { passRepo.unpass("b") } returns ApiResult.Success(
            PassedPage(listOf(passed("a")), truncated = true, nextCursor = "c2")
        )
        val vm = PassedViewModel(passRepo)
        idle()
        vm.loadMore()
        idle()
        assertEquals(listOf("a", "b"), vm.uiState.value.passed.map { it.userId })

        vm.release("b")
        idle()

        assertEquals(
            "the reader's own place in the walk stays where they put it",
            listOf("a"), vm.uiState.value.passed.map { it.userId },
        )
        assertEquals("c3", vm.uiState.value.nextCursor)
        assertEquals(2, vm.uiState.value.pages)
        assertEquals("Пётр", vm.uiState.value.released)
    }

    @Test
    fun `a release on the first page takes the page the write answered`() = runTest {
        coEvery { passRepo.passed(null) } returns ApiResult.Success(
            PassedPage(listOf(passed("a"), passed("b")), truncated = false, nextCursor = null)
        )
        coEvery { passRepo.unpass("a") } returns ApiResult.Success(
            PassedPage(listOf(passed("c")), truncated = true, nextCursor = "c9")
        )
        val vm = PassedViewModel(passRepo)
        idle()

        vm.release("a")
        idle()

        assertEquals(listOf("c"), vm.uiState.value.passed.map { it.userId })
        assertEquals("c9", vm.uiState.value.nextCursor)
        assertTrue(vm.uiState.value.truncated)
    }

    @Test
    fun `a refused release keeps the person on the list and says so`() = runTest {
        coEvery { passRepo.passed(null) } returns ApiResult.Success(
            PassedPage(listOf(passed("a")), truncated = false, nextCursor = null)
        )
        coEvery { passRepo.unpass("a") } returns fail(code = "not_found", text = "Вы не пропускали этого человека.")
        val vm = PassedViewModel(passRepo)
        idle()

        vm.release("a")
        idle()

        assertEquals(listOf("a"), vm.uiState.value.passed.map { it.userId })
        assertTrue(vm.uiState.value.error!!.contains("Вы не пропускали этого человека."))
        assertNull(vm.uiState.value.released)
    }

    // ---------------------------------------------------------------- the pair list

    @Test
    fun `the pair list reads a page and keeps the link to the rest of the account's pairs`() = runTest {
        coEvery { matchRepo.matches(null) } returns ApiResult.Success(
            MatchesPage(listOf(pair("m1")), truncated = true, nextCursor = "p2")
        )
        val vm = MatchesViewModel(matchRepo)
        idle()

        assertEquals(1, vm.uiState.value.matches.size)
        assertEquals("p2", vm.uiState.value.nextCursor)
        assertTrue("a page is not the account's whole list", vm.uiState.value.truncated)
    }

    @Test
    fun `pairs arrive behind the link, and a dissolved pair leaves the walk in place`() = runTest {
        coEvery { matchRepo.matches(null) } returns ApiResult.Success(
            MatchesPage(listOf(pair("m1")), truncated = true, nextCursor = "p2")
        )
        coEvery { matchRepo.matches("p2") } returns ApiResult.Success(
            MatchesPage(listOf(pair("m2"), pair("m3")), truncated = false, nextCursor = null)
        )
        coEvery { matchRepo.dissolve("m2") } returns ApiResult.Success(Unit)
        val vm = MatchesViewModel(matchRepo)
        idle()
        vm.loadMore()
        idle()

        assertEquals(listOf("m1", "m2", "m3"), vm.uiState.value.matches.map { it.matchId })
        assertEquals(PageTail.End, pageTail(vm.uiState.value.walk()))

        vm.askDissolve(vm.uiState.value.matches.first { it.matchId == "m2" })
        vm.confirmDissolve()
        idle()

        assertEquals(listOf("m1", "m3"), vm.uiState.value.matches.map { it.matchId })
        assertFalse("a dissolved pair leaves the rows the reader holds readable", vm.uiState.value.isEmpty)
        assertEquals(
            "the walk is still where the reader left it, and the door says nothing stands behind it",
            PageTail.End, pageTail(vm.uiState.value.walk()),
        )
    }

    @Test
    fun `a silent refresh starts the walk over from the newest page`() = runTest {
        coEvery { matchRepo.matches(null) } returnsMany listOf(
            ApiResult.Success(MatchesPage(listOf(pair("m1")), truncated = true, nextCursor = "p2")),
            ApiResult.Success(MatchesPage(listOf(pair("m9")), truncated = false, nextCursor = null)),
        )
        coEvery { matchRepo.matches("p2") } returns ApiResult.Success(
            MatchesPage(listOf(pair("m2")), truncated = false, nextCursor = null)
        )
        val vm = MatchesViewModel(matchRepo)
        idle()
        vm.loadMore()
        idle()
        assertEquals(listOf("m1", "m2"), vm.uiState.value.matches.map { it.matchId })

        vm.refreshSilently()
        idle()

        assertEquals("the refresh asked what the list looks like now, so the top of it is the answer",
            listOf("m9"), vm.uiState.value.matches.map { it.matchId })
        assertEquals(1, vm.uiState.value.pages)
        assertNull(vm.uiState.value.nextCursor)
    }

    @Test
    fun `a refused pair link restarts from the newest page instead of repeating a dead key`() = runTest {
        coEvery { matchRepo.matches(null) } returnsMany listOf(
            ApiResult.Success(MatchesPage(listOf(pair("m1")), truncated = true, nextCursor = "p2")),
            ApiResult.Success(MatchesPage(listOf(pair("m8")), truncated = false, nextCursor = null)),
        )
        coEvery { matchRepo.matches("p2") } returns
            fail(code = BROKEN_PAGE_LINK_CODE, text = "Продолжить список не удалось.")
        val vm = MatchesViewModel(matchRepo)
        idle()
        vm.loadMore()
        idle()

        vm.retryMore()
        idle()

        coVerify(exactly = 2) { matchRepo.matches(null) }
        assertEquals(listOf("m8"), vm.uiState.value.matches.map { it.matchId })
        assertNull(vm.uiState.value.moreError)
    }
}
