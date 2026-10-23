package app.befos.presentation.discovery

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.OutgoingLike
import app.befos.domain.model.OutgoingLikesPage
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
 * The account's own read of the taps it left standing, and the one verb that takes a tap back.
 *
 * The wire shape lives in [app.befos.data.repository.MyLikesReadTest]; what is pinned here is the
 * conversation, and it is kept as carefully apart as the inbox and the pass list keep theirs: the list
 * the server gave, a read that never came back, and a list that came back holding nothing. The last is
 * the account's real history and the second is not — a page that drew «вы пока никого не лайкали» over
 * a timeout would tell a person their hearts are gone because a request failed.
 *
 * The withdrawal is held to the same bargain the release of a pass struck. The server answers the
 * DELETE with the list that survives, so the page paints that answer instead of subtracting the tapped
 * row: a tap the write refused has to stay visible with a working verb, and a row removed on a refusal
 * would be a gesture the account never took back, drawn as one it did. One case splits that bargain,
 * and it is the case the cursor made: once the reader has walked past the first page, the page the
 * write returns describes rows they have already read, so the row leaves the list and the frontier
 * stays where the reader put it.
 *
 * The walk is the family these checks grew around (stage 123). Two asks of one link are one request; a
 * page that fails keeps the rows above it and names itself as the missing half; the same face coming
 * back on two pages is drawn once; and a list never ends with a promise — the line that says what is
 * shown counts the rows this device holds, because the server never said how many taps the account
 * made.
 *
 * The deck is deliberately absent from these checks, and that is the difference between this verb and
 * the inbox's reply. Answering a tap makes a person answered; taking a tap back un-makes it, so the
 * person becomes eligible again and the deck finds them at its next refill by itself. The screen
 * therefore publishes nothing to [app.befos.domain.safety.AnsweredUsers] — and says so on its own row.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class MyLikesViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val repo: DiscoveryRepository = mockk()

    private fun row(
        id: String,
        name: String = id,
        age: Int = 31,
        city: String = "Казань",
        percent: Int? = 78,
        likedAt: String = "2026-10-19T06:00:00+00:00",
        photoUrl: String? = "https://host/uploads/$id.png",
    ) = OutgoingLike(
        userId = id,
        name = name,
        age = age,
        city = city,
        photoUrl = photoUrl,
        compatibility = percent,
        likedAt = likedAt,
    )

    private fun open(
        vararg rows: OutgoingLike,
        truncated: Boolean = false,
        nextCursor: String? = null,
    ): MyLikesViewModel {
        coEvery { repo.liked() } returns
            ApiResult.Success(OutgoingLikesPage(rows.toList(), truncated, nextCursor))
        return MyLikesViewModel(repo).also { mainRule.testDispatcher.scheduler.advanceUntilIdle() }
    }

    @Test
    fun `the list the server gives is the list the page holds, in the order it gave it`() = runTest {
        val vm = open(row("b"), row("a"))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Newest tap first, as the rows arrive: the page invents no sort of its own.
        assertEquals(listOf("b", "a"), vm.uiState.value.likes.map { it.userId })
        assertEquals(false, vm.uiState.value.truncated)
        assertEquals(false, vm.uiState.value.loading)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `a read that never came back is not drawn as nobody having been liked`() = runTest {
        coEvery { repo.liked() } returns
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")

        val vm = MyLikesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // «Вы пока никого не лайкали» is a fact about the account, and a timeout says nothing about it.
        assertEquals(emptyList<OutgoingLike>(), vm.uiState.value.likes)
        assertEquals(false, vm.uiState.value.isEmpty)
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.error)
    }

    @Test
    fun `an account that has liked nobody is drawn as one once the server says so`() = runTest {
        val vm = open()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.isEmpty)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `a page that ran out says it ran out`() = runTest {
        val rows = (1..50).map { row("u$it") }
        coEvery { repo.liked() } returns ApiResult.Success(OutgoingLikesPage(rows, truncated = true))
        val vm = MyLikesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The server stopped at fifty and named no cursor, so the screen holds the flag and asks for
        // nothing: inventing a link of its own is how a device starts paging against a door that cannot
        // answer it.
        assertEquals(50, vm.uiState.value.likes.size)
        assertEquals(true, vm.uiState.value.truncated)
        assertEquals(false, vm.uiState.value.canLoadMore)
        assertNull(vm.uiState.value.nextCursor)
    }

    @Test
    fun `taking a tap back paints the list the write returned and names who left it`() = runTest {
        val vm = open(row("b", name = "Борис"), row("a", name = "Анна"))
        coEvery { repo.unlike("b") } returns
            ApiResult.Success(OutgoingLikesPage(listOf(row("a", name = "Анна")), truncated = false))

        vm.withdraw("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("a"), vm.uiState.value.likes.map { it.userId })
        assertEquals(false, vm.uiState.value.busy)
        assertNull(vm.uiState.value.error)
        // The row is gone the moment the write lands, so the notice has to carry the name out of it: a
        // message pointing at nobody leaves the reader wondering whether the tap did anything.
        assertEquals("Борис", vm.uiState.value.withdrawn)
        coVerify(exactly = 1) { repo.liked() }
    }

    @Test
    fun `a refused withdrawal keeps the person on the page and calls the tap unrevoked`() = runTest {
        val vm = open(row("b"))
        coEvery { repo.unlike("b") } returns
            ApiResult.Error(404, "Вы этого человека не лайкали. Обновите список.")

        vm.withdraw("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The row is the only evidence the account has that it tapped this person; hiding it on a write
        // the server refused would erase a gesture that is still written.
        assertEquals(listOf("b"), vm.uiState.value.likes.map { it.userId })
        assertEquals(false, vm.uiState.value.busy)
        assertNull(vm.uiState.value.withdrawn)
        assertTrue(vm.uiState.value.error.orEmpty(), vm.uiState.value.error!!.contains("Лайк не отозван"))
        assertTrue(vm.uiState.value.error.orEmpty(), vm.uiState.value.error!!.contains("не лайкали"))
    }

    @Test
    fun `a withdrawal whose server page still holds the person keeps the row visible`() = runTest {
        val vm = open(row("b"), row("a"))
        // The page the write returns is the server's answer even when it surprises this screen: a list
        // that still names the person is drawn as one that still names them.
        coEvery { repo.unlike("b") } returns
            ApiResult.Success(OutgoingLikesPage(listOf(row("b"), row("a")), truncated = false))

        vm.withdraw("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("b", "a"), vm.uiState.value.likes.map { it.userId })
        assertEquals("b", vm.uiState.value.withdrawn)
    }

    @Test
    fun `the percent the tap was made with survives the withdrawal`() = runTest {
        val vm = open(row("b", percent = 91), row("a", percent = 62))
        coEvery { repo.unlike("b") } returns
            ApiResult.Success(OutgoingLikesPage(listOf(row("a", percent = 62)), truncated = false))

        vm.withdraw("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The screen holds the server's rows, so a number that was read off a like row stays read off it
        // rather than being rebuilt here — the percent is the reason the tap happened, not a guess.
        assertEquals(62, vm.uiState.value.likes.single().compatibility)
        assertEquals("Совместимость 62%", myLikesScoreWord(vm.uiState.value.likes.single()))
    }

    @Test
    fun `a withdrawal that lands clears the refusal the earlier tap left`() = runTest {
        val vm = open(row("b"), row("a"))
        coEvery { repo.unlike("b") } returns ApiResult.Error(404, "Вы этого человека не лайкали. Обновите список.")
        vm.withdraw("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.error != null)

        coEvery { repo.unlike("a") } returns
            ApiResult.Success(OutgoingLikesPage(listOf(row("b")), truncated = false))
        vm.withdraw("a")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // A stale refusal line sitting over a list the server has just redrawn would read as if the
        // second tap had failed too.
        assertNull(vm.uiState.value.error)
        assertEquals(listOf("b"), vm.uiState.value.likes.map { it.userId })
        assertEquals("a", vm.uiState.value.withdrawn)
    }

    @Test
    fun `the notice once read stays read`() = runTest {
        val vm = open(row("b", name = "Борис"))
        coEvery { repo.unlike("b") } returns
            ApiResult.Success(OutgoingLikesPage(emptyList(), truncated = false))

        vm.withdraw("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.dismissWithdrawn()

        assertNull(vm.uiState.value.withdrawn)
        assertFalse(vm.uiState.value.loading)
    }

    @Test
    fun `a second withdrawal while the first is out is one write`() = runTest {
        val vm = open(row("b"), row("a"))
        val gate = CompletableDeferred<Unit>()
        coEvery { repo.unlike("b") } coAnswers {
            gate.await()
            ApiResult.Success(OutgoingLikesPage(listOf(row("a")), truncated = false))
        }

        vm.withdraw("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.withdraw("a")

        coVerify(exactly = 1) { repo.unlike(any()) }
        assertEquals(true, vm.uiState.value.busy)

        gate.complete(Unit)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(false, vm.uiState.value.busy)
        coVerify(exactly = 0) { repo.unlike("a") }
    }

    @Test
    fun `refreshing the page reads the list again and paints what comes back`() = runTest {
        coEvery { repo.liked() } returnsMany listOf(
            ApiResult.Success(OutgoingLikesPage(listOf(row("b")), truncated = false)),
            ApiResult.Success(OutgoingLikesPage(listOf(row("c"), row("b")), truncated = false)),
        )
        val vm = MyLikesViewModel(repo)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("b"), vm.uiState.value.likes.map { it.userId })

        // The page does not watch the list on its own: a tap taken back on another device reaches this
        // screen through the read the truncation notice offers, the way the inbox does.
        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("c", "b"), vm.uiState.value.likes.map { it.userId })
        coVerify(exactly = 2) { repo.liked() }
    }

    @Test
    fun `the page behind the first one joins the rows on the screen in the order the server gave them`() =
        runTest {
            val vm = open(row("a"), row("b"), truncated = true, nextCursor = "c1")

            coEvery { repo.liked("c1") } returns ApiResult.Success(
                OutgoingLikesPage(listOf(row("c"), row("d")), truncated = false, nextCursor = null),
            )
            vm.loadMore()
            mainRule.testDispatcher.scheduler.advanceUntilIdle()

            assertEquals(listOf("a", "b", "c", "d"), vm.uiState.value.likes.map { it.userId })
            assertEquals(2, vm.uiState.value.pages)
            assertEquals(false, vm.uiState.value.truncated)
            assertEquals(false, vm.uiState.value.loadingMore)
            assertNull(vm.uiState.value.moreError)
            coVerify(exactly = 1) { repo.liked("c1") }
        }

    @Test
    fun `scrolling to the end twice while a page is out asks the server once`() = runTest {
        val vm = open(row("a"), truncated = true, nextCursor = "c1")
        val gate = CompletableDeferred<Unit>()
        coEvery { repo.liked("c1") } coAnswers {
            gate.await()
            ApiResult.Success(OutgoingLikesPage(listOf(row("b")), truncated = false))
        }

        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.loadMore()
        vm.loadMore()

        assertEquals(true, vm.uiState.value.loadingMore)
        coVerify(exactly = 1) { repo.liked("c1") }

        gate.complete(Unit)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("a", "b"), vm.uiState.value.likes.map { it.userId })
    }

    @Test
    fun `a page that did not arrive leaves the rows the screen holds and says which half is missing`() =
        runTest {
            val vm = open(row("a"), row("b"), truncated = true, nextCursor = "c1")
            coEvery { repo.liked("c1") } returns
                ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")

            vm.loadMore()
            mainRule.testDispatcher.scheduler.advanceUntilIdle()

            // The account's own history did not shrink because its older half timed out: the rows stay,
            // the link stays, and the failure is drawn where the missing rows would have been.
            assertEquals(listOf("a", "b"), vm.uiState.value.likes.map { it.userId })
            assertEquals("c1", vm.uiState.value.nextCursor)
            assertEquals(true, vm.uiState.value.canLoadMore)
            assertTrue(vm.uiState.value.moreError.orEmpty().contains("Сервер недоступен"))
            assertNull(vm.uiState.value.error)
            assertEquals(false, vm.uiState.value.loadingMore)
        }

    @Test
    fun `repeating the failed page asks the same link and appends once`() = runTest {
        val vm = open(row("a"), truncated = true, nextCursor = "c1")
        coEvery { repo.liked("c1") } returnsMany listOf(
            ApiResult.Error(500, "Сервер недоступен."),
            ApiResult.Success(OutgoingLikesPage(listOf(row("b")), truncated = false)),
        )

        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("a", "b"), vm.uiState.value.likes.map { it.userId })
        assertNull(vm.uiState.value.moreError)
        assertEquals(2, vm.uiState.value.pages)
    }

    @Test
    fun `a row the next page names twice enters the list once`() = runTest {
        val vm = open(row("a"), row("b"), truncated = true, nextCursor = "c1")
        // A person the account liked again between two pages wrote a fresh row, and the keyset happily
        // reads the gesture twice. A list that showed the same face twice would be this screen's bug.
        coEvery { repo.liked("c1") } returns ApiResult.Success(
            OutgoingLikesPage(listOf(row("b"), row("c")), truncated = false),
        )

        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("a", "b", "c"), vm.uiState.value.likes.map { it.userId })
    }

    @Test
    fun `a tap taken back from a deep page leaves the walk where the reader put it`() = runTest {
        val vm = open(row("a"), row("b"), truncated = true, nextCursor = "c1")
        coEvery { repo.liked("c1") } returns ApiResult.Success(
            OutgoingLikesPage(listOf(row("c"), row("d")), truncated = true, nextCursor = "c2"),
        )
        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(2, vm.uiState.value.pages)

        // The write answers the newest page, which this reader walked past two requests ago: adopting it
        // would drop the rows below and drag the frontier back to the top of the list.
        coEvery { repo.unlike("b") } returns ApiResult.Success(
            OutgoingLikesPage(listOf(row("a"), row("c")), truncated = true, nextCursor = "c9"),
        )
        vm.withdraw("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("a", "c", "d"), vm.uiState.value.likes.map { it.userId })
        assertEquals("c2", vm.uiState.value.nextCursor)
        assertEquals(2, vm.uiState.value.pages)
        assertEquals("b", vm.uiState.value.withdrawn)
        coVerify(exactly = 0) { repo.liked("c2") }
    }

    @Test
    fun `reloading the list starts the walk again from the newest tap`() = runTest {
        val vm = open(row("a"), truncated = true, nextCursor = "c1")
        coEvery { repo.liked("c1") } returns ApiResult.Success(
            OutgoingLikesPage(listOf(row("b")), truncated = false, nextCursor = null),
        )
        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("a", "b"), vm.uiState.value.likes.map { it.userId })

        coEvery { repo.liked() } returns ApiResult.Success(
            OutgoingLikesPage(listOf(row("z")), truncated = false, nextCursor = null),
        )
        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The reader asked what the server holds now, and the older pages answered an earlier question:
        // they leave with the reload rather than sitting under a list that no longer matches.
        assertEquals(listOf("z"), vm.uiState.value.likes.map { it.userId })
        assertEquals(1, vm.uiState.value.pages)
        assertNull(vm.uiState.value.nextCursor)
    }

    @Test
    fun `the row that is on the wire says so while the others stay lit`() = runTest {
        val vm = open(row("a", name = "Анна"), row("b", name = "Борис"))
        val gate = CompletableDeferred<Unit>()
        coEvery { repo.unlike("a") } coAnswers {
            gate.await()
            ApiResult.Success(OutgoingLikesPage(listOf(row("b")), truncated = false))
        }

        vm.withdraw("a")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // One write, one row that knows it: a list that greyed itself row by row would read as a
        // history the app had refused to draw.
        assertEquals("a", vm.uiState.value.withdrawing)
        assertEquals(true, vm.uiState.value.busy)

        gate.complete(Unit)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertNull(vm.uiState.value.withdrawing)
        assertEquals(false, vm.uiState.value.busy)
    }

    @Test
    fun `the line under the list counts the rows the walk gathered, not a total nobody named`() {
        assertEquals(
            "Показано 50 касаний, и список идёт дальше",
            myLikesShownWord(50, truncated = true),
        )
        assertEquals(
            "Показано 87 касаний — весь список",
            myLikesShownWord(87, truncated = false),
        )
        // The server never answers how many taps an account has, and a «из N» invented here would be a
        // number about nothing — the mistake defect 72-1 named for an empty compatibility band.
        assertFalse(myLikesShownWord(12, truncated = false).contains("из"))
    }

    @Test
    fun `the row's second line names the day the server wrote`() {
        val moscow = ZoneId.of("Europe/Moscow")

        assertEquals(
            "31 · Казань · 19 октября 2026",
            myLikesRowWord(row("b", likedAt = "2026-10-19T06:00:00+00:00"), moscow),
        )
        // The day belongs to the reader, not to UTC: a card swiped to the heart late in the evening of
        // one calendar day is already the next morning for a person three hours ahead.
        assertEquals(
            "31 · Казань · 20 октября 2026",
            myLikesRowWord(row("b", likedAt = "2026-10-19T23:30:00+00:00"), moscow),
        )
    }

    @Test
    fun `the row's second line drops the day the server did not write`() {
        val moscow = ZoneId.of("Europe/Moscow")

        // An unreadable instant is not a day to print, and inventing one would date somebody's gesture.
        assertEquals("31 · Казань", myLikesRowWord(row("b", likedAt = ""), moscow))
        assertEquals("31 · Казань", myLikesRowWord(row("b", likedAt = "вечер зачёта"), moscow))
    }

    @Test
    fun `the row's third line says the percent is missing instead of borrowing a zero`() {
        // A row written before percents were stored on likes carries none. Zero would read as a card the
        // account tapped against all evidence, which is defect 72-1 dressed in the account's own list.
        assertEquals("Процент не записан", myLikesScoreWord(row("b", percent = null)))
        assertEquals("Совместимость 78%", myLikesScoreWord(row("b", percent = 78)))
        assertEquals("Совместимость 0%", myLikesScoreWord(row("b", percent = 0)))
    }

    @Test
    fun `the door into the page is named by the one word the app uses for it`() {
        // The deck's header, the profile tab and this screen's own top bar all say it, and a second
        // label for the same route would be a second door the person has to learn.
        assertEquals("Кого вы лайкнули", app.befos.presentation.common.myLikesEntryWord())
    }
}
