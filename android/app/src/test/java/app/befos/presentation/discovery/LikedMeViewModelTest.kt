package app.befos.presentation.discovery

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.IncomingLike
import app.befos.domain.model.LikeOutcome
import app.befos.domain.model.LikedMePage
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.safety.AnsweredUsers
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import io.mockk.verify
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
 * The account's own read of who tapped it, held by the screen that shows it.
 *
 * The conversation is pinned here; the wire shape is [app.befos.data.repository.IncomingLikesReadTest].
 * Three answers have to stay distinguishable: the list the server gave, a read that never came back,
 * and a list that came back holding nothing. The last is the account's real state and the second is
 * not — a page that drew «пока никто не лайкнул» over a failed read would tell a person nobody is
 * interested because a request timed out.
 *
 * The answer is the other half. A row leaves the list only once the server recorded the like, so a
 * refused write keeps the person on the page and the notice says the answer was not counted; and the
 * deck is told about the answered id, because the same person can be waiting there as a card whose
 * next tap answers «Профиль не найден».
 */
@OptIn(ExperimentalCoroutinesApi::class)
class LikedMeViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val repo: DiscoveryRepository = mockk()
    // The real signal would need a collector racing the publish; what is pinned here is that this
    // screen sends the id at all, and the deck's half of the flow is DiscoveryViewModelTest.
    private val answered: AnsweredUsers = mockk(relaxed = true)

    private fun like(
        id: String,
        name: String = id,
        compatibility: Int? = 88,
        likedAt: String = "2026-10-19T06:00:00+00:00",
        photoUrl: String? = "https://host/uploads/$id.png",
    ) = IncomingLike(
        userId = id,
        name = name,
        age = 31,
        city = "Казань",
        photoUrl = photoUrl,
        compatibility = compatibility,
        likedAt = likedAt,
    )

    private fun open(vararg rows: IncomingLike, truncated: Boolean = false): LikedMeViewModel {
        coEvery { repo.likedMe() } returns ApiResult.Success(LikedMePage(rows.toList(), truncated))
        return LikedMeViewModel(repo, answered).also { mainRule.testDispatcher.scheduler.advanceUntilIdle() }
    }

    @Test
    fun `the list the server gives is the list the page holds, in the order it gave it`() = runTest {
        val vm = open(like("b"), like("a"))
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("b", "a"), vm.uiState.value.likes.map { it.userId })
        assertEquals(false, vm.uiState.value.truncated)
        assertEquals(false, vm.uiState.value.loading)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `a read that never came back is not drawn as nobody having liked the account`() = runTest {
        coEvery { repo.likedMe() } returns
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")

        val vm = LikedMeViewModel(repo, answered)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // «Пока никто не лайкнул» is a fact about the account, and a timeout says nothing about it.
        assertEquals(emptyList<IncomingLike>(), vm.uiState.value.likes)
        assertEquals(false, vm.uiState.value.isEmpty)
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.error)
    }

    @Test
    fun `an account nobody has liked is drawn as one once the server says so`() = runTest {
        val vm = open()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(true, vm.uiState.value.isEmpty)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `a page that ran out says it ran out`() = runTest {
        val rows = (1..50).map { like("u$it", compatibility = 50) }
        val vm = open(truncated = true)
        coEvery { repo.likedMe() } returns ApiResult.Success(LikedMePage(rows, truncated = true))
        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The server stopped at fifty and names no cursor, so the page cannot promise the rest is here.
        assertEquals(50, vm.uiState.value.likes.size)
        assertEquals(true, vm.uiState.value.truncated)
    }

    @Test
    fun `answering a tap takes the row out and tells the deck that person is answered`() = runTest {
        val vm = open(like("b"), like("a"))
        coEvery { repo.like("b") } returns
            ApiResult.Success(LikeOutcome(matched = false, matchId = null, compatibility = null))

        vm.respond("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("a"), vm.uiState.value.likes.map { it.userId })
        assertEquals(false, vm.uiState.value.busy)
        assertNull(vm.uiState.value.error)
        assertNull(vm.uiState.value.match)
        verify(exactly = 1) { answered.publish("b") }
        // The page is the server's list, not a copy of the deck: a like written here needs no re-read
        // to stay honest, and paying for one would be a second request for what the row just said.
        coVerify(exactly = 1) { repo.likedMe() }
    }

    @Test
    fun `a refused answer keeps the person on the page and calls the answer uncounted`() = runTest {
        val vm = open(like("b"))
        coEvery { repo.like("b") } returns ApiResult.Error(429, "Слишком много запросов. Подождите немного.")

        vm.respond("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The row is the only evidence the account has that this person tapped; removing it on a write
        // the server refused would lose the tap rather than answer it.
        assertEquals(listOf("b"), vm.uiState.value.likes.map { it.userId })
        assertEquals(false, vm.uiState.value.busy)
        assertTrue(vm.uiState.value.error.orEmpty(), vm.uiState.value.error!!.contains("Ответ не записан"))
        assertTrue(vm.uiState.value.error.orEmpty(), vm.uiState.value.error!!.contains("Слишком много запросов"))
        verify(exactly = 0) { answered.publish(any()) }
    }

    @Test
    fun `the match the answer formed carries the words of the row that left the list`() = runTest {
        val vm = open(like("b", name = "Борис"))
        coEvery { repo.like("b") } returns
            ApiResult.Success(LikeOutcome(matched = true, matchId = "m-7", compatibility = 91))

        vm.respond("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The row is gone the moment the pair forms, so the moment keeps the name and the photograph
        // with it: a dialog over an emptied list would describe a match nobody can see.
        assertEquals("Борис", vm.uiState.value.match?.name)
        assertEquals("https://host/uploads/b.png", vm.uiState.value.match?.photoUrl)
        assertEquals("m-7", vm.uiState.value.match?.matchId)
        assertEquals(91, vm.uiState.value.match?.compatibility)
        assertEquals(emptyList<IncomingLike>(), vm.uiState.value.likes)
    }

    @Test
    fun `a matched answer whose pair id never arrived opens no door`() = runTest {
        val vm = open(like("b"))
        coEvery { repo.like("b") } returns
            ApiResult.Success(LikeOutcome(matched = true, matchId = null, compatibility = 91))

        vm.respond("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The like was recorded, so the row leaves the list; only the door is withheld. A dialog that
        // offers a pair the client cannot name is a button that goes nowhere.
        assertNull(vm.uiState.value.match)
        assertEquals(emptyList<IncomingLike>(), vm.uiState.value.likes)
        verify(exactly = 1) { answered.publish("b") }
    }

    @Test
    fun `the moment once closed stays closed`() = runTest {
        val vm = open(like("b"))
        coEvery { repo.like("b") } returns
            ApiResult.Success(LikeOutcome(matched = true, matchId = "m-7", compatibility = 91))

        vm.respond("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.dismissMatch()

        assertNull(vm.uiState.value.match)
        assertFalse(vm.uiState.value.loading)
    }

    @Test
    fun `a second answer while the first is out is one write`() = runTest {
        val vm = open(like("b"), like("a"))
        val gate = CompletableDeferred<Unit>()
        coEvery { repo.like("b") } coAnswers {
            gate.await()
            ApiResult.Success(LikeOutcome(matched = false, matchId = null, compatibility = null))
        }

        vm.respond("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.respond("a")

        coVerify(exactly = 1) { repo.like(any()) }
        assertEquals(true, vm.uiState.value.busy)

        gate.complete(Unit)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(false, vm.uiState.value.busy)
        coVerify(exactly = 0) { repo.like("a") }
    }

    @Test
    fun `refreshing the page reads the list again and paints what comes back`() = runTest {
        coEvery { repo.likedMe() } returnsMany listOf(
            ApiResult.Success(LikedMePage(listOf(like("b")), truncated = false)),
            ApiResult.Success(LikedMePage(listOf(like("c"), like("b")), truncated = false)),
        )
        val vm = LikedMeViewModel(repo, answered)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("b"), vm.uiState.value.likes.map { it.userId })

        // The page does not watch the list on its own: a tap that arrived while it was open reaches
        // the person through this read, and the truncation notice says so in the same words.
        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("c", "b"), vm.uiState.value.likes.map { it.userId })
        coVerify(exactly = 2) { repo.likedMe() }
    }

    @Test
    fun `the row's second line names the day the server wrote`() {
        val moscow = ZoneId.of("Europe/Moscow")

        assertEquals(
            "31 · Казань · 19 октября 2026",
            likedRowWord(like("b", likedAt = "2026-10-19T06:00:00+00:00"), moscow),
        )
        // The day belongs to the reader, not to UTC: a tap written late in the evening of one calendar
        // day is already the next morning for a person three hours ahead.
        assertEquals(
            "31 · Казань · 20 октября 2026",
            likedRowWord(like("b", likedAt = "2026-10-19T23:30:00+00:00"), moscow),
        )
    }

    @Test
    fun `the row's second line drops the day the server did not write`() {
        val moscow = ZoneId.of("Europe/Moscow")

        // An unreadable instant is not a day to print, and inventing one would date somebody's tap.
        assertEquals("31 · Казань", likedRowWord(like("b", likedAt = ""), moscow))
        assertEquals("31 · Казань", likedRowWord(like("b", likedAt = "вечер зачёта"), moscow))
    }

    @Test
    fun `the row's third line is the percent the tap carried or the sentence that says none`() {
        assertEquals("Совместимость 88%", likedScoreWord(like("b", compatibility = 88)))
        // Never zero, never «ещё не посчитано»: the row was written before percents were stored on
        // likes, and a number the tapper never saw is not this account's to show.
        assertEquals("Процент не записан", likedScoreWord(like("b", compatibility = null)))
        assertEquals("Совместимость 0%", likedScoreWord(like("b", compatibility = 0)))
    }

    @Test
    fun `the door into the page is named by the one word the app uses for it`() {
        // The deck's header and the profile tab both lead here, and a second label for the same route
        // would be a second door the person has to learn.
        assertEquals("Кто вас лайкнул", app.befos.presentation.common.likedMeEntryWord())
    }
}
