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
 * A refusal speaks on the write channel and never on the read one. Both say «something did not come
 * back», and only one of them is true: the read of the account's history answered perfectly well, and
 * the gesture the reader asked for did not land. Until stage 123 they shared a field, and the body of
 * the screen — which resolves a read error into its own full-height card — replaced a list the server
 * still held with «Не удалось прочитать ваши лайки» whose only verb re-read a page that had never
 * failed. The row a refusal belongs to is kept beside its sentence so that «Повторить» repeats that tap
 * rather than starting a fresh read.
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
    fun `a refused withdrawal speaks on the write channel and leaves the read alone`() = runTest {
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
        assertTrue(vm.uiState.value.writeError.orEmpty(), vm.uiState.value.writeError!!.contains("Лайк не отозван"))
        assertTrue(vm.uiState.value.writeError.orEmpty(), vm.uiState.value.writeError!!.contains("не лайкали"))
        // A refused write is not a failed read. Until stage 123 separated them the screen put this
        // sentence in the read channel, and its body drew «Не удалось прочитать ваши лайки» over a list
        // the account still holds — a card the reader had to dismiss by re-reading a page that had never
        // stopped answering.
        assertNull(vm.uiState.value.error)
        assertEquals("b", vm.uiState.value.withdrawFailed)
    }

    @Test
    fun `a refused withdrawal does not ask the reader to reload the list it just answered`() = runTest {
        val vm = open(row("b"), row("a"), truncated = true, nextCursor = "c1")
        coEvery { repo.unlike("b") } returns ApiResult.Error(404, "Вы этого человека не лайкали.")

        vm.withdraw("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The write failed for one row. The read is whole, so the walk stays walkable: the link the last
        // page handed over still reaches the taps behind it, and the reader is not sent back to the top.
        assertEquals(true, vm.uiState.value.canLoadMore)
        assertEquals("c1", vm.uiState.value.nextCursor)
        assertEquals(1, vm.uiState.value.pages)
        assertEquals(MyLikesBody.Rows, myLikesBody(vm.uiState.value))
        // The one read this screen made is the one it made on opening. A refusal that asked the door
        // again would be the old behaviour wearing a new field, and the count is the only place where
        // «the notice does not reload the list» is visible from outside.
        coVerify(exactly = 1) { repo.liked(null) }
        // The notice's verb has one target, and it is the row the refusal named — not the first row of
        // the list, not the reader's place, not nothing.
        assertEquals("b", myLikesWriteRetryTarget(vm.uiState.value))
        assertNull(myLikesWriteRetryTarget(vm.uiState.value.copy(withdrawFailed = null, writeError = null)))
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
        assertTrue(vm.uiState.value.writeError != null)

        coEvery { repo.unlike("a") } returns
            ApiResult.Success(OutgoingLikesPage(listOf(row("b")), truncated = false))
        vm.withdraw("a")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // A stale refusal line sitting over a list the server has just redrawn would read as if the
        // second tap had failed too.
        assertNull(vm.uiState.value.writeError)
        assertNull(vm.uiState.value.withdrawFailed)
        assertNull(vm.uiState.value.error)
        assertEquals(listOf("b"), vm.uiState.value.likes.map { it.userId })
        assertEquals("a", vm.uiState.value.withdrawn)
    }

    @Test
    fun `the notice repeats the very tap the server refused and lets it through`() = runTest {
        val vm = open(row("b", name = "Борис"), row("a"))
        coEvery { repo.unlike("b") } returnsMany listOf(
            ApiResult.Error(404, "Вы этого человека не лайкали. Обновите список."),
            ApiResult.Success(OutgoingLikesPage(listOf(row("a")), truncated = false)),
        )

        vm.withdraw("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("b", vm.uiState.value.withdrawFailed)

        // The word «Повторить» on the notice has to repeat the gesture it names. A retry that re-read the
        // list would answer a refused write with a page, and the reader would have to find the row again.
        vm.withdraw(vm.uiState.value.withdrawFailed!!)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("a"), vm.uiState.value.likes.map { it.userId })
        assertNull(vm.uiState.value.writeError)
        assertNull(vm.uiState.value.withdrawFailed)
        assertEquals("Борис", vm.uiState.value.withdrawn)
        coVerify(exactly = 2) { repo.unlike("b") }
    }

    @Test
    fun `a withdrawal asked for while a page is on the wire is not sent`() = runTest {
        val vm = open(row("a"), row("b"), truncated = true, nextCursor = "c1")
        val gate = CompletableDeferred<Unit>()
        coEvery { repo.liked("c1") } coAnswers {
            gate.await()
            ApiResult.Success(OutgoingLikesPage(listOf(row("c")), truncated = false, nextCursor = null))
        }

        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.loadingMore)

        // The page in flight is an answer about rows this screen has already promised to show. A write
        // that lands while it is out redraws the same list from the server's newest page, and the page
        // still to come then appends rows that overlap the one the write returned — the reader loses a
        // name in the seam. One request at a time is the rule the two asks of one link already follow.
        vm.withdraw("a")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        coVerify(exactly = 0) { repo.unlike(any()) }
        assertEquals(true, vm.uiState.value.loadingMore)

        gate.complete(Unit)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("a", "b", "c"), vm.uiState.value.likes.map { it.userId })

        coEvery { repo.unlike("a") } returns
            ApiResult.Success(OutgoingLikesPage(listOf(row("b"), row("c")), truncated = false))
        vm.withdraw("a")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        coVerify(exactly = 1) { repo.unlike("a") }
    }

    @Test
    fun `a reload that fails drops the frontier but keeps saying the list goes further`() = runTest {
        val vm = open(row("a"), truncated = true, nextCursor = "c1")
        coEvery { repo.liked("c1") } returns ApiResult.Success(
            OutgoingLikesPage(listOf(row("b")), truncated = true, nextCursor = "c2"),
        )
        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("c2", vm.uiState.value.nextCursor)

        coEvery { repo.liked("c2") } returns ApiResult.Error(-1, "Страница не дошла.")
        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Страница не дошла.", vm.uiState.value.moreError)

        coEvery { repo.liked() } returns ApiResult.Error(-1, "Сервер недоступен.")
        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // A reload asks the server what the list holds now. When that answer does not come, the link the
        // earlier walk left behind describes a page the reload was going to replace: keeping it would let
        // «Показать ещё» hand a stale cursor to a door whose newest page this screen no longer knows.
        assertNull(vm.uiState.value.nextCursor)
        assertEquals(false, vm.uiState.value.canLoadMore)
        // What the last answer that did come said about the rest of the list survives. A reload that
        // failed does not unmake it, and erasing it here made the tail print «Дальше ваших касаний нет»
        // and the counter «весь список» over a history this account had not finished reading.
        assertEquals(true, vm.uiState.value.truncated)
        // The refusal of a page goes with the key that page needed. The reload's own failure is named
        // above the rows, and a notice left standing without its cursor is a word nobody can use.
        assertNull(vm.uiState.value.moreError)
        // The count of pages is not part of what is dropped: the rows on the screen still came from two
        // reads, and a withdrawal decides by that number whether the write's answer is the whole list or
        // only the row that left it. Zeroing it here would make the next withdrawal replace a walked list
        // with the server's first page — the rows below it disappearing under a reader who never asked.
        assertEquals(2, vm.uiState.value.pages)
        // The rows stay: they are the account's own taps, read once already, and a failed refresh does
        // not unmake them.
        assertEquals(listOf("a", "b"), vm.uiState.value.likes.map { it.userId })
        assertEquals("Сервер недоступен.", vm.uiState.value.error)
        assertEquals(MyLikesBody.Rows, myLikesBody(vm.uiState.value))
        assertEquals(MyLikesTail.WaitingForReread, myLikesTail(vm.uiState.value))
    }

    @Test
    fun `a write that answered the first page closes the page that never came`() = runTest {
        val vm = open(row("a"), truncated = true, nextCursor = "c1")
        coEvery { repo.liked("c1") } returns ApiResult.Error(-1, "Страница не дошла.")
        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Страница не дошла.", vm.uiState.value.moreError)

        coEvery { repo.unlike("a") } returns
            ApiResult.Success(OutgoingLikesPage(emptyList(), truncated = false))
        vm.withdraw("a")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The write answered this very page, so the screen knows again where its own list ends. The link
        // the refusal was waiting for is gone with the rows it pointed at, and the notice about that
        // refusal has nothing left to repeat: «Повторить» on it would ask for a page this list no longer
        // has, and the walk's gate would answer by doing nothing at all.
        assertEquals("a", vm.uiState.value.withdrawn)
        assertNull(vm.uiState.value.nextCursor)
        assertNull(vm.uiState.value.moreError)
        assertEquals(MyLikesTail.Nothing, myLikesTail(vm.uiState.value))
    }

    @Test
    fun `the tail offers no verb unless the key that verb needs is on the screen`() {
        val held = listOf(row("a"), row("b"))
        val walked = MyLikesUiState(
            loading = false, likes = held, truncated = true, nextCursor = "c2", pages = 2,
        )
        assertEquals(MyLikesTail.MoreAvailable, myLikesTail(walked))
        assertEquals(MyLikesTail.PageRefused, myLikesTail(walked.copy(moreError = "Страница не дошла.")))
        assertEquals(MyLikesTail.Loading, myLikesTail(walked.copy(loadingMore = true, moreError = null)))
        // The end of the walk is the server's sentence about what stands beyond these rows, not the
        // absence of a key: it is drawn once the last answer said there is nothing further.
        assertEquals(MyLikesTail.End, myLikesTail(walked.copy(truncated = false, nextCursor = null)))
        // A reload that failed leaves the screen holding no key while the list still goes on. That is the
        // state the tail used to answer with «Дальше ваших касаний нет» — and, with a page refusal still
        // standing, with a «Повторить» pointed at a page whose link had just been thrown away.
        assertEquals(
            MyLikesTail.WaitingForReread,
            myLikesTail(walked.copy(nextCursor = null, error = "Сервер недоступен.")),
        )
        assertEquals(
            MyLikesTail.WaitingForReread,
            myLikesTail(walked.copy(nextCursor = null, moreError = "Страница не дошла.")),
        )
        // The first page, read to its end: nothing has to be said under it.
        assertEquals(
            MyLikesTail.Nothing,
            myLikesTail(MyLikesUiState(loading = false, likes = held, pages = 1)),
        )
    }

    @Test
    fun `a withdrawal after a failed reload keeps the pages the reader walked through`() = runTest {
        val vm = open(row("a"), truncated = true, nextCursor = "c1")
        coEvery { repo.liked("c1") } returns ApiResult.Success(
            OutgoingLikesPage(listOf(row("b")), truncated = true, nextCursor = "c2"),
        )
        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coEvery { repo.liked() } returns ApiResult.Error(-1, "Сервер недоступен.")
        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coEvery { repo.unlike("b") } returns ApiResult.Success(
            OutgoingLikesPage(listOf(row("z"), row("y")), truncated = true, nextCursor = "c9"),
        )
        vm.withdraw("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The walk this screen made is still the walk it holds: the write answers a page from the top of
        // the list, and adopting that page would trade two rows the reader reached for two they never saw.
        assertEquals(listOf("a"), vm.uiState.value.likes.map { it.userId })
        assertEquals(2, vm.uiState.value.pages)
        assertNull(vm.uiState.value.nextCursor)
        assertEquals("b", vm.uiState.value.withdrawn)
        coVerify(exactly = 1) { repo.unlike("b") }
    }

    @Test
    fun `the body of the list is the rows whenever the account holds rows`() {
        val held = listOf(row("a"))
        val readFailed = MyLikesUiState(
            loading = false,
            likes = held,
            error = "Сервер недоступен.",
            nextCursor = "c1",
            pages = 1,
        )
        // Rows before failure: the notice above them says which read did not come, and the history the
        // device holds stays on the screen. This is the branch the write channel was invented for — a
        // refused tap used to reach here as a read error and replace the list with its own card.
        assertEquals(MyLikesBody.Rows, myLikesBody(readFailed))
        assertEquals(MyLikesBody.ReadFailure, myLikesBody(readFailed.copy(likes = emptyList())))
        assertEquals(MyLikesBody.Skeleton, myLikesBody(MyLikesUiState(likes = held)))
        assertEquals(MyLikesBody.Empty, myLikesBody(MyLikesUiState(loading = false)))
        assertEquals(
            MyLikesBody.Rows,
            myLikesBody(readFailed.copy(error = null, writeError = "Лайк не отозван.", withdrawFailed = "a")),
        )
        // A walk that ended with nothing left to read is drawn as the rows it gathered, not as a failure.
        assertEquals(MyLikesBody.Rows, myLikesBody(readFailed.copy(error = null, nextCursor = null, pages = 3)))
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
            // Живой прогон показал, что этотexpectation был дефектом, а не поведением: дверь
            // `/discover/liked` отвечала 503 через четыре секунды, триггер у края списка снова читал
            // `canLoadMore` истинным — курсор-то остался — и просил страницу заново, и заново, и заново.
            // Хвост пять минут держал «Догружаю ваши касания…» и ни разу не показал отметку с
            // «Повторить», то есть читатель не мог ни узнать об отказе, ни сделать шаг сам. Автоматический
            // обход и человеческий тап не могут стоять на одних воротах: скролл останавливается на
            // первом отказе, а повторить имеет право только глагол на отметке.
            assertEquals(false, vm.uiState.value.canLoadMore)
            assertTrue(vm.uiState.value.moreError.orEmpty().contains("Сервер недоступен"))
            assertNull(vm.uiState.value.error)
            assertEquals(false, vm.uiState.value.loadingMore)
        }

    /**
     * The gate the walk at the bottom of the list reads has to be closed by a refusal, while the verb on
     * the notice still reaches the server — both halves are the same five lines of state, and only one of
     * them was measured on a device.
     */
    @Test
    fun `a refused page closes the automatic walk and leaves the notices verb working`() = runTest {
        val vm = open(row("a"), truncated = true, nextCursor = "c1")
        coEvery { repo.liked("c1") } returns ApiResult.Error(503, "Сервер недоступен.")

        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(false, vm.uiState.value.canLoadMore)
        assertEquals("c1", vm.uiState.value.nextCursor)
        coVerify(exactly = 1) { repo.liked("c1") }

        coEvery { repo.liked("c1") } returns
            ApiResult.Success(OutgoingLikesPage(listOf(row("b")), truncated = false))
        vm.loadMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("a", "b"), vm.uiState.value.likes.map { it.userId })
        assertNull(vm.uiState.value.moreError)
        // Два обращения за весь прогон: одно принес отказ, второе принёс человек, нажавший «Повторить».
        coVerify(exactly = 2) { repo.liked("c1") }
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
