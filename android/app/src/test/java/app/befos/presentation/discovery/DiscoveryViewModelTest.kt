package app.befos.presentation.discovery

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.DiscoveryCard
import app.befos.domain.model.DiscoveryEmpty
import app.befos.domain.model.DiscoveryPage
import app.befos.domain.model.LikeOutcome
import app.befos.domain.model.WaitlistStatus
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.repository.ReferralRepository
import app.befos.domain.repository.SafetyRepository
import app.befos.domain.safety.AnsweredUsers
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class DiscoveryViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val repo: DiscoveryRepository = mockk()
    // Only the complaint form the deck now holds touches it; the cases here that do not report
    // never stub it, and a strict mock is what keeps an unintended send from passing silently.
    private val safety: SafetyRepository = mockk()
    // Only the waiting mark touches it; the swipe cases never stub it.
    private val referrals: ReferralRepository = mockk(relaxed = true)

    // The real signal, not a mock: what matters here is that a card answered on another
    // screen reaches the deck through the flow the two ViewModels share.
    private val answered = AnsweredUsers()

    private fun card(id: String) = DiscoveryCard(
        userId = id, name = id, age = 25, city = "Москва", about = null,
        datingGoal = "relationship", photoUrl = null, interests = emptyList(),
        compatibility = 80, sharedInterestsCount = 2,
    )

    private fun pageOf(vararg ids: String, nextCursor: String? = null, hasMore: Boolean = false) =
        ApiResult.Success(
            DiscoveryPage(ids.map(::card), nextCursor, hasMore)
        )

    private fun emptyPage(
        reason: String,
        audience: String = "none",
        nearby: String = "none",
        preparingHere: Boolean = false,
        canWiden: Boolean = false,
        waitlistJoined: Boolean = false,
        waitlistCity: String? = null,
    ) = ApiResult.Success(
        DiscoveryPage(
            cards = emptyList(),
            nextCursor = null,
            hasMore = false,
            empty = DiscoveryEmpty(
                reason = reason,
                audience = audience,
                nearby = nearby,
                someonePreparingHere = preparingHere,
                canWidenFilters = canWiden,
                waitlistJoined = waitlistJoined,
                waitlistCity = waitlistCity,
            ),
        ),
    )

    @Test
    fun `like without match advances to next card`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b", "c")
        coEvery { repo.like("a") } returns ApiResult.Success(LikeOutcome(matched = false, matchId = null, compatibility = null))
        coEvery { repo.pass(any()) } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("a", vm.uiState.value.current?.userId)

        vm.like()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("b", vm.uiState.value.current?.userId)
        assertNull(vm.uiState.value.match)
    }

    @Test
    fun `mutual like surfaces match dialog`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b")
        coEvery { repo.like("a") } returns ApiResult.Success(LikeOutcome(matched = true, matchId = "m1", compatibility = 91))

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.like()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertNotNull(vm.uiState.value.match)
        assertEquals("m1", vm.uiState.value.match?.matchId)
        // Card should not advance until the dialog is dismissed.
        assertEquals("a", vm.uiState.value.current?.userId)

        vm.dismissMatch()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertNull(vm.uiState.value.match)
        assertEquals("b", vm.uiState.value.current?.userId)
    }

    @Test
    fun `a refused like names the card that comes back instead of quoting the transport`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b")
        coEvery { repo.like("a") } returns ApiResult.Error(0, "Нет соединения")
        coEvery { repo.pass(any()) } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.like()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The fling already carried the card off the screen before the write was asked for, so
        // a bare transport line leaves the viewer staring at an empty deck area, a counter that
        // did not move, and no sentence saying which person is still there.
        assertEquals(
            "Ответ не записан — карточка вернулась. Нет соединения",
            vm.uiState.value.error,
        )
    }

    @Test
    fun `the card a refused like left behind is the one the screen has to bring back`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b")
        coEvery { repo.like("a") } returns ApiResult.Error(0, "Нет соединения")

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.like()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The index never moved, so this is still the current card; the flag is what tells the
        // screen that the fling has to be undone rather than followed by the next person.
        assertEquals("a", vm.uiState.value.current?.userId)
        assertEquals("a", vm.uiState.value.rejectedCard)
        // A deck still marked busy swallows every further tap, so the refusal must release it.
        assertFalse(vm.uiState.value.busy)
    }

    @Test
    fun `a refused pass says the same about the card it would have thrown away`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b")
        coEvery { repo.pass("a") } returns ApiResult.Error(-1, "Сервер недоступен")

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.pass()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(
            "Ответ не записан — карточка вернулась. Сервер недоступен",
            vm.uiState.value.error,
        )
        assertEquals("a", vm.uiState.value.current?.userId)
        assertEquals("a", vm.uiState.value.rejectedCard)
        assertEquals(0, vm.uiState.value.index)
    }

    @Test
    fun `a card that came back is answered by the next tap`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b")
        coEvery { repo.like("a") } returnsMany listOf(
            ApiResult.Error(0, "Нет соединения"),
            ApiResult.Success(LikeOutcome(matched = false, matchId = null, compatibility = null)),
        )

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.like()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("a", vm.uiState.value.rejectedCard)

        vm.like()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Retrying from the same card is the whole recovery: the notice clears, the flag goes
        // with the answer that landed, and the deck moves on to the next person.
        assertEquals("b", vm.uiState.value.current?.userId)
        assertNull(vm.uiState.value.rejectedCard)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `a successful answer does not leave a stale card to bring back`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b", "c")
        coEvery { repo.pass("a") } returns ApiResult.Error(0, "Нет соединения")
        coEvery { repo.like("a") } returns ApiResult.Success(LikeOutcome(matched = false, matchId = null, compatibility = null))

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.pass()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("a", vm.uiState.value.rejectedCard)

        vm.like()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The screen springs back the card whose id is still in the flag; leaving "a" there
        // after an answer that did land would drag the new card off screen for no reason.
        assertEquals("b", vm.uiState.value.current?.userId)
        assertNull(vm.uiState.value.rejectedCard)
    }

    @Test
    fun `reloading the deck drops the card that never got an answer`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b")
        coEvery { repo.like("a") } returns ApiResult.Error(0, "Нет соединения")

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.like()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("a", vm.uiState.value.rejectedCard)

        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // A fresh deck starts from the top, so a flag pointing at the previous attempt would
        // make the screen chase a card it is no longer showing.
        assertNull(vm.uiState.value.rejectedCard)
        assertNull(vm.uiState.value.error)
        assertEquals("a", vm.uiState.value.current?.userId)
    }

    @Test
    fun `the next page is asked for with the cursor the server returned`() = runTest {
        coEvery { repo.feed(any(), null) } returns pageOf("a", "b", nextCursor = "r1", hasMore = true)
        coEvery { repo.feed(any(), "r1") } returns pageOf("c", nextCursor = "r2", hasMore = false)
        coEvery { repo.pass(any()) } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(listOf("a", "b"), vm.uiState.value.cards.map { it.userId })

        // Two swipes put the viewer near the end of the first page, which is where the
        // next page is asked for.
        vm.pass()
        vm.pass()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("a", "b", "c"), vm.uiState.value.cards.map { it.userId })
        coVerify(exactly = 1) { repo.feed(any(), "r1") }
    }

    @Test
    fun `a deck that said it was over is not asked again`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b", nextCursor = null, hasMore = false)
        coEvery { repo.pass(any()) } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.pass()
        vm.pass()
        vm.pass()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // One call for the page itself; swiping past its end must not keep requesting a
        // second one, because the answer that there is nothing more has already been given.
        coVerify(exactly = 1) { repo.feed(any(), any()) }
        assertEquals(listOf("a", "b"), vm.uiState.value.cards.map { it.userId })
    }

    @Test
    fun `feed error surfaces message`() = runTest {
        coEvery { repo.feed(any(), any()) } returns ApiResult.Error(-1, "Нет подключения к интернету.")
        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("Нет подключения к интернету.", vm.uiState.value.error)
    }

    @Test
    fun `a page that did not arrive is reported while the loaded cards stay`() = runTest {
        coEvery { repo.feed(any(), null) } returns pageOf("a", "b", "c", nextCursor = "r1", hasMore = true)
        coEvery { repo.feed(any(), "r1") } returns ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз.")
        coEvery { repo.pass(any()) } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.pass()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The deck goes on with what is already loaded; the failure is about what comes next.
        assertEquals(listOf("a", "b", "c"), vm.uiState.value.cards.map { it.userId })
        assertEquals("b", vm.uiState.value.current?.userId)
        assertEquals(null, vm.uiState.value.error)
        assertEquals("Сервер недоступен. Проверьте соединение и попробуйте ещё раз.", vm.uiState.value.feedError)
    }

    @Test
    fun `retrying a page that did not arrive asks for the cursor it never got`() = runTest {
        coEvery { repo.feed(any(), null) } returns pageOf("a", "b", "c", nextCursor = "r1", hasMore = true)
        coEvery { repo.feed(any(), "r1") } returnsMany listOf(
            ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
            pageOf("d", nextCursor = "r2", hasMore = false),
        )
        coEvery { repo.pass(any()) } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.pass()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertNotNull(vm.uiState.value.feedError)

        vm.fetchMore()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The cursor did not move, so the retry asks for the same page instead of skipping it.
        coVerify(exactly = 2) { repo.feed(any(), "r1") }
        assertEquals(listOf("a", "b", "c", "d"), vm.uiState.value.cards.map { it.userId })
        assertEquals(null, vm.uiState.value.feedError)
    }

    @Test
    fun `a deck that ran out on its own does not warn about a failed page`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b", nextCursor = null, hasMore = false)
        coEvery { repo.pass(any()) } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.pass()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.pass()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The screen only claims it showed everyone when the server actually said so.
        assertNull(vm.uiState.value.current)
        assertNull(vm.uiState.value.feedError)
    }

    @Test
    fun `a card answered on the profile screen leaves the deck`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b", "c")

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        answered.publish("b")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Blocking or passing happens on that other screen, whose ViewModel is not this one;
        // without the shared signal the person you just removed is the next card, and the tap
        // on them answers «Профиль не найден».
        assertEquals(listOf("a", "c"), vm.uiState.value.cards.map { it.userId })
        assertEquals("a", vm.uiState.value.current?.userId)
    }

    @Test
    fun `answering the card on screen slides the next one into its place`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b", "c")

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        answered.publish("a")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("b", "c"), vm.uiState.value.cards.map { it.userId })
        assertEquals("b", vm.uiState.value.current?.userId)
    }

    @Test
    fun `answering a card that was already seen does not move the deck backwards`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b", "c")
        coEvery { repo.pass(any()) } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.pass()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals("b", vm.uiState.value.current?.userId)

        answered.publish("a")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The removed card sat before the current one, so the current card keeps its slot
        // instead of the deck jumping back to a person already passed.
        assertEquals(listOf("b", "c"), vm.uiState.value.cards.map { it.userId })
        assertEquals("b", vm.uiState.value.current?.userId)
    }

    @Test
    fun `an answer about someone the deck never held changes nothing`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a", "b", "c")

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        answered.publish("someone-else")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(listOf("a", "b", "c"), vm.uiState.value.cards.map { it.userId })
        assertEquals("a", vm.uiState.value.current?.userId)
    }

    @Test
    fun `a deck whose last card was answered elsewhere ends instead of pointing past it`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("a")

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        answered.publish("a")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertNull(vm.uiState.value.current)
        assertTrue(vm.uiState.value.isEmpty)
    }

    @Test
    fun `an empty page keeps the server's reason instead of inventing one`() = runTest {
        coEvery { repo.feed(any(), any()) } returns emptyPage(
            reason = "audience_preparing",
            preparingHere = true,
            waitlistJoined = true,
            waitlistCity = "Москва",
        )

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals("audience_preparing", vm.uiState.value.empty?.reason)
        assertEquals(true, vm.uiState.value.empty?.someonePreparingHere)
        assertTrue(vm.uiState.value.isEmpty)
        // The mark is the server's: the screen reads it back instead of assuming a fresh device
        // never joined a list.
        assertEquals(true, vm.uiState.value.waitlist?.joined)
        assertEquals("Москва", vm.uiState.value.waitlist?.city)
    }

    @Test
    fun `joining and leaving the waitlist read back the server's city`() = runTest {
        coEvery { repo.feed(any(), any()) } returns emptyPage("no_one_yet")
        coEvery { referrals.joinWaitlist(null) } returns
            ApiResult.Success(WaitlistStatus(joined = true, city = "Казань"))
        coEvery { referrals.leaveWaitlist() } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.joinWaitlist()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.waitlist?.joined)
        assertEquals("Казань", vm.uiState.value.waitlist?.city)
        assertEquals("Казань", vm.uiState.value.empty?.waitlistCity)

        vm.leaveWaitlist()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(false, vm.uiState.value.waitlist?.joined)
        assertNull(vm.uiState.value.waitlist?.city)
        assertNull(vm.uiState.value.empty?.waitlistCity)
    }

    @Test
    fun `a refused waitlist write does not replace the empty deck with an error`() = runTest {
        coEvery { repo.feed(any(), any()) } returns emptyPage("no_one_yet")
        coEvery { referrals.joinWaitlist(null) } returns ApiResult.Error(0, "Нет соединения")

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.joinWaitlist()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The deck's own state is still the server's explanation; a failed side action lives beside
        // it, where it can be retried without throwing the person back to a blank pane.
        assertEquals("no_one_yet", vm.uiState.value.empty?.reason)
        assertEquals("Нет соединения", vm.uiState.value.waitlistError)
        assertNull(vm.uiState.value.error)
        assertFalse(vm.uiState.value.waitlistBusy)

        coEvery { referrals.joinWaitlist(null) } returns
            ApiResult.Success(WaitlistStatus(joined = true, city = null))
        vm.joinWaitlist()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.waitlist?.joined)
        assertNull(vm.uiState.value.waitlistError)
    }

    @Test
    fun `answering the last loaded card is distinguishable from an empty first page`() = runTest {
        coEvery { repo.feed(any(), any()) } returns pageOf("only")
        coEvery { repo.pass(any()) } returns ApiResult.Success(Unit)

        val vm = DiscoveryViewModel(repo, safety, answered, referrals)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertFalse(vm.uiState.value.reviewedAllLoaded)

        vm.pass()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertNull(vm.uiState.value.current)
        assertNull(vm.uiState.value.empty)
        // A fact this client can state without the server: the cards it was given were answered.
        assertTrue(vm.uiState.value.reviewedAllLoaded)
    }
}
