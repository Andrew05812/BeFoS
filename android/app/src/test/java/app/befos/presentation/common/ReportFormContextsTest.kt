package app.befos.presentation.common

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.DiscoveryCard
import app.befos.domain.model.DiscoveryPage
import app.befos.domain.model.LikeOutcome
import app.befos.domain.model.Message
import app.befos.domain.model.PublicProfile
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.DiscoveryRepository
import app.befos.domain.repository.MatchRepository
import app.befos.domain.repository.ProfileRepository
import app.befos.domain.repository.SafetyRepository
import app.befos.domain.repository.TestRepository
import app.befos.domain.safety.AnsweredUsers
import app.befos.presentation.chat.ChatViewModel
import app.befos.presentation.discovery.DiscoveryViewModel
import app.befos.presentation.publicprofile.PublicProfileViewModel
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * The one complaint form, reached from the three places a person is seen.
 *
 * Stage 101 gave the profile screen a flag; stage 102 gives the deck and a conversation the same
 * entry. What the three have to agree on is not the layout but the writing: which id the complaint
 * names, what a second tap does while the first is still open, what the person is told afterwards,
 * and that nothing about the moderator's decision ever reaches them. Those are asserted here, once
 * per context, because each context resolves the id differently — the card on screen, the partner a
 * pair route answered with, the card a route named.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ReportFormContextsTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private fun advance() = mainRule.testDispatcher.scheduler.advanceUntilIdle()

    private fun deckCard(id: String) = DiscoveryCard(
        userId = id, name = id, age = 25, city = "Москва", about = null,
        datingGoal = "relationship", photoUrl = null, interests = emptyList(),
        compatibility = 80, sharedInterestsCount = 2,
    )

    private fun card(id: String) = PublicProfile(
        userId = id, name = "Борис", age = 31, city = "Казань", about = "О себе.",
        datingGoal = "relationship", gender = "male", interests = emptyList(),
        photoUrls = emptyList(), compatibility = 68, categories = emptyList(),
        sharedInterests = emptyList(),
    )

    private fun message() = Message(
        id = "1", matchId = "m1", senderId = "them", body = "hi",
        createdAt = "2026-01-01T00:00:01", isRead = false, isOwn = false,
    )

    private fun deck(safety: SafetyRepository, vararg ids: String): DiscoveryViewModel {
        val repo: DiscoveryRepository = mockk {
            coEvery { feed(any(), any()) } returns ApiResult.Success(
                DiscoveryPage(ids.map(::deckCard), null, false)
            )
            coEvery { like(any()) } returns ApiResult.Success(
                LikeOutcome(matched = false, matchId = null, compatibility = null)
            )
            coEvery { pass(any()) } returns ApiResult.Success(Unit)
        }
        return DiscoveryViewModel(repo, safety, AnsweredUsers())
    }

    private fun thread(
        safety: SafetyRepository,
        partner: ApiResult<PublicProfile>,
        history: ApiResult<List<Message>>,
    ): ChatViewModel {
        val matches: MatchRepository = mockk {
            coEvery { partner(any()) } returns partner
        }
        val chat: ChatRepository = mockk {
            every { socket(any()) } returns MutableSharedFlow()
            coEvery { history(any(), any()) } returns history
            coEvery { markRead(any()) } returns ApiResult.Success(Unit)
            coEvery { sendTyping(any(), any()) } returns Unit
        }
        return ChatViewModel(chat, matches, safety, "m1")
    }

    private fun profileScreen(safety: SafetyRepository): PublicProfileViewModel {
        val profiles: ProfileRepository = mockk {
            coEvery { publicProfile("u-1") } returns ApiResult.Success(card("u-1"))
        }
        val tests: TestRepository = mockk()
        return PublicProfileViewModel(
            profiles,
            mockk(relaxed = true),
            safety,
            mockk(relaxed = true),
            mockk(relaxed = true),
            tests,
            userId = "u-1",
        )
    }

    /** Accepts every complaint and hands back nothing but the fact that it was stored. */
    private fun accepting(): SafetyRepository = mockk {
        coEvery { report(any(), any(), any()) } returns ApiResult.Success(Unit)
    }

    @Test
    fun `a complaint from the deck names the card on screen`() = runTest {
        val safety = accepting()
        val reported = slot<String>()
        coEvery { safety.report(capture(reported), any(), any()) } returns ApiResult.Success(Unit)
        val vm = deck(safety, "a", "b")
        advance()

        vm.askReport()
        vm.report.setReason("spam")
        vm.report.submit()
        advance()

        assertEquals("a", reported.captured)
        assertEquals(true, vm.report.state.value.sent)
    }

    @Test
    fun `the deck keeps showing the same card while a complaint is written and sent`() = runTest {
        // A complaint is not an answer about the person: it must not read as a pass. The card that
        // was flagged stays on screen, so the viewer still decides likes and passes themselves.
        val safety = accepting()
        val vm = deck(safety, "a", "b")
        advance()

        vm.askReport()
        assertEquals("a", vm.uiState.value.current?.userId)
        vm.report.setReason("harassment")
        vm.report.submit()
        advance()
        vm.closeReport()
        advance()

        assertEquals(0, vm.uiState.value.index)
        assertEquals("a", vm.uiState.value.current?.userId)
        assertEquals(listOf("a", "b"), vm.uiState.value.cards.map { it.userId })
        assertEquals(false, vm.uiState.value.busy)
        assertNull(vm.uiState.value.error)
    }

    @Test
    fun `the complaint keeps the card it was opened on after the deck moves on`() = runTest {
        // The id is captured at the tap, not at the send: a like lands while the form is still open,
        // the next card slides in, and the complaint must still name the person who was flagged.
        val safety = accepting()
        val reported = slot<String>()
        coEvery { safety.report(capture(reported), any(), any()) } returns ApiResult.Success(Unit)
        val vm = deck(safety, "a", "b")
        advance()

        vm.askReport()
        vm.like()
        advance()
        assertEquals("b", vm.uiState.value.current?.userId)

        vm.report.setReason("fake")
        vm.report.submit()
        advance()

        assertEquals("a", reported.captured)
    }

    @Test
    fun `a complaint from a conversation names the partner the pair route answered with`() = runTest {
        // The thread knows a match id, and a complaint needs a person. Only `partner(matchId)`
        // carries the id, which is why the flag stays dark until that card arrives.
        val safety = accepting()
        val reported = slot<String>()
        coEvery { safety.report(capture(reported), any(), any()) } returns ApiResult.Success(Unit)
        val vm = thread(
            safety,
            ApiResult.Success(card("u-9")),
            ApiResult.Success(listOf(message())),
        )
        advance()

        vm.askReport()
        vm.report.setReason("threats")
        vm.report.submit()
        advance()

        assertEquals("u-9", reported.captured)
    }

    @Test
    fun `a conversation that cannot carry messages can still send a complaint`() = runTest {
        // The pair dissolved, so the composer is gone. The reason to report someone is usually
        // written in the messages that arrived before it did, so the entry cannot live with them.
        val safety = accepting()
        coEvery { safety.report(any(), any(), any()) } returns ApiResult.Success(Unit)
        val vm = thread(
            safety,
            ApiResult.Success(card("u-9")),
            ApiResult.Error(404, "match not found"),
        )
        advance()
        assertEquals(true, vm.uiState.value.gone)

        vm.askReport()
        vm.report.setReason("harassment")
        vm.report.submit()
        advance()

        assertEquals(true, vm.report.state.value.open)
        assertEquals(true, vm.report.state.value.sent)
        coVerify(exactly = 1) { safety.report("u-9", "harassment", null) }
    }

    @Test
    fun `a thread whose partner card never arrived has no one to report`() = runTest {
        // Without the card the client holds only the pair id, and a complaint written against that
        // would name nobody. Asking has to leave the form shut rather than send a wrong target.
        val safety = accepting()
        val vm = thread(
            safety,
            ApiResult.Error(404, "no partner"),
            ApiResult.Success(listOf(message())),
        )
        advance()
        assertNull(vm.uiState.value.partnerUserId)

        vm.askReport()
        advance()

        assertEquals(false, vm.report.state.value.open)
        coVerify(exactly = 0) { safety.report(any(), any(), any()) }
    }

    @Test
    fun `a complaint sent from a profile leaves the card only when the dialog is closed`() = runTest {
        // The send used to pop the screen by itself, so the person never saw whether the complaint
        // went out. Now the dialog answers first and this tap is the way out.
        val safety = accepting()
        val vm = profileScreen(safety)
        advance()

        vm.openReport()
        vm.setReportReason("inappropriate")
        vm.submitReport()
        advance()

        assertEquals(true, vm.report.state.value.sent)
        assertEquals(false, vm.uiState.value.gone)

        vm.closeReport()
        assertEquals(true, vm.uiState.value.gone)
    }

    @Test
    fun `a cancelled complaint keeps the person on their card`() = runTest {
        val safety = accepting()
        val vm = profileScreen(safety)
        advance()

        vm.openReport()
        vm.closeReport()
        advance()

        assertEquals(false, vm.report.state.value.open)
        assertEquals(false, vm.uiState.value.gone)
        coVerify(exactly = 0) { safety.report(any(), any(), any()) }
    }

    @Test
    fun `the confirmation says only that the complaint went out`() = runTest {
        // Same words in all three contexts because they come from the same form: the reason and the
        // note stay as written, and nothing about a queue position or a moderator's decision appears.
        val safety = accepting()
        val vm = deck(safety, "a")
        advance()

        vm.askReport()
        vm.report.setReason("impersonation")
        vm.report.setDetails("анкета взята из другой сети")
        vm.report.submit()
        advance()

        val state = vm.report.state.value
        assertEquals(true, state.sent)
        assertEquals(true, state.open)
        assertEquals(false, state.sending)
        assertEquals("impersonation", state.reason)
        assertEquals("анкета взята из другой сети", state.details)
        assertNull(state.error)
    }

    @Test
    fun `a second tap while the first is in flight asks the server once`() = runTest {
        val safety = mockk<SafetyRepository> {
            coEvery { report(any(), any(), any()) } coAnswers {
                delay(10)
                ApiResult.Success(Unit)
            }
        }
        val vm = deck(safety, "a")
        advance()

        vm.askReport()
        vm.report.setReason("spam")
        vm.report.submit()
        vm.report.submit()
        advance()

        coVerify(exactly = 1) { safety.report("a", "spam", null) }
        assertEquals(true, vm.report.state.value.sent)
    }

    @Test
    fun `a refused complaint stays open holding what was written`() = runTest {
        val safety: SafetyRepository = mockk {
            coEvery { report(any(), any(), any()) } returns ApiResult.Error(429, "too many complaints")
        }
        val vm = deck(safety, "a")
        advance()

        vm.askReport()
        vm.report.setReason("spam")
        vm.report.setDetails("ещё раз")
        vm.report.submit()
        advance()

        val state = vm.report.state.value
        assertEquals(true, state.open)
        assertEquals(false, state.sent)
        assertEquals(false, state.sending)
        assertEquals("ещё раз", state.details)
        assertEquals("too many complaints", state.error)
        assertEquals("a", vm.uiState.value.current?.userId)
    }

    @Test
    fun `nothing is sent while no reason from the list is chosen`() = runTest {
        val safety = accepting()
        val vm = deck(safety, "a")
        advance()

        vm.askReport()
        vm.report.submit()
        advance()

        assertEquals("Выберите причину из списка.", vm.report.state.value.error)
        assertFalse(vm.report.state.value.sent)
        coVerify(exactly = 0) { safety.report(any(), any(), any()) }
    }

    @Test
    fun `a note longer than the server accepts is cut while it is typed`() = runTest {
        // The bound is the server's own, so a long account of a bad evening comes back as a
        // complaint rather than as a validation error the reader cannot fix.
        val safety = accepting()
        val vm = deck(safety, "a")
        advance()

        vm.askReport()
        vm.report.setDetails("д".repeat(MaxReportDetails + 400))

        assertEquals(MaxReportDetails, vm.report.state.value.details.length)
    }

    @Test
    fun `the reasons offered are the reasons the server accepts`() = runTest {
        // Mirrors `VALID_REASONS` in `backend/app/services/safety_service.py`. A slug the client
        // invents would be refused at write time, and one the client leaves out is a category a
        // moderator never hears about.
        assertEquals(
            setOf(
                "spam", "harassment", "inappropriate", "fake", "minor",
                "impersonation", "threats", "other",
            ),
            ReportReasonLabels.keys,
        )
    }
}
