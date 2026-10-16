package app.befos.presentation.recommendations

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Activity
import app.befos.domain.model.Recommendation
import app.befos.domain.repository.MatchRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class RecommendationsViewModelTest {

    @get:Rule
    val mainRule = MainDispatcherRule()

    private val cinema = Activity(id = 7, slug = "cinema", title = "Поход в кино", description = null, category = "culture")
    private val rec = Recommendation(
        activity = cinema, score = 63, position = 1, reasons = emptyList(), selected = false,
        partnerSelected = false, declined = false,
        myMeetingTime = null, partnerMeetingTime = null, iAcceptedTime = null, agreedTime = null,
    )
    private val boardGames = Activity(
        id = 8, slug = "board_games", title = "Вечер настольных игр", description = null, category = "leisure",
    )
    private val recBoard = Recommendation(
        activity = boardGames, score = 58, position = 2, reasons = emptyList(), selected = false,
        partnerSelected = false, declined = false,
        myMeetingTime = null, partnerMeetingTime = null, iAcceptedTime = null, agreedTime = null,
    )

    private fun matchRepo() = mockk<MatchRepository> {
        coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec))
        coEvery { selectRecommendation("m1", 7) } returns ApiResult.Success(Unit)
    }

    private fun viewModel(match: MatchRepository = matchRepo()): RecommendationsViewModel {
        val vm = RecommendationsViewModel(match, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        return vm
    }

    @Test
    fun `an idea tap is one request and marks the card`() = runTest {
        // The one request is the pair's plan, and the plan is what carries the idea into their chat:
        // the route writes the journal line of its own kind in the same transaction, so the tab has
        // no sentence of its own to type and the pair cannot read one idea twice.
        val match = matchRepo()
        val vm = viewModel(match)

        vm.select(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { match.selectRecommendation("m1", 7) }
        assertTrue(vm.uiState.value.selected.contains(7))
        assertNull(vm.uiState.value.selectError)
    }

    @Test
    fun `tapping the same idea twice records it once`() = runTest {
        val match = matchRepo()
        val vm = viewModel(match)

        vm.select(7)
        vm.select(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { match.selectRecommendation("m1", 7) }
    }

    @Test
    fun `a card the page reports as chosen opens chosen and takes no request`() = runTest {
        // The state a second visit to the tab starts from: the choice this person recorded for
        // this pair comes back on the page, so the tab has to be opened before the mark exists.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec.copy(selected = true)))
        }
        val vm = viewModel(match)

        assertTrue(vm.uiState.value.selected.contains(7))

        vm.select(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 0) { match.selectRecommendation(any(), any()) }
    }

    @Test
    fun `an idea the partner proposed is joined by the same one request`() = runTest {
        // What used to be a sentence of its own («Я тоже за: …») is now the plan's own news: the
        // page says whose idea this is, the button reads «Поддержать в чате», and the write behind
        // it is the same one — the pair's plan gains the second half and says so in the thread.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns
                ApiResult.Success(listOf(rec.copy(partnerSelected = true)))
            coEvery { selectRecommendation("m1", 7) } returns ApiResult.Success(Unit)
        }
        val vm = viewModel(match)

        vm.select(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { match.selectRecommendation("m1", 7) }
        assertTrue(vm.uiState.value.selected.contains(7))
        assertNull(vm.uiState.value.selectError)
    }

    @Test
    fun `an idea the server refused comes back unmarked and names the reason`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec))
            coEvery { selectRecommendation("m1", 7) } returns ApiResult.Error(0, "Нет соединения")
        }
        val vm = viewModel(match)

        vm.select(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Nothing half-landed: the idea is neither in the pair's chat nor on their plan, so the
        // card returns to where the tap can be made again and the notice says what was lost.
        assertTrue(vm.uiState.value.selected.isEmpty())
        assertEquals("Не удалось отправить идею в чат. Нет соединения", vm.uiState.value.selectError)
    }

    @Test
    fun `a page that reports the idea to the pair retires the notice`() = runTest {
        // The answer of a send can be lost while the idea itself reached the pair, so the next page
        // is the fact that ends the doubt: the plan is on the pair and nothing is missing.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returnsMany listOf(
                ApiResult.Success(listOf(rec)),
                ApiResult.Success(listOf(rec.copy(selected = true))),
            )
            coEvery { selectRecommendation("m1", 7) } returns ApiResult.Error(0, "Нет соединения")
        }
        val vm = viewModel(match)

        vm.select(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertNotNull(vm.uiState.value.selectError)

        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertNull(vm.uiState.value.selectError)
        assertTrue(vm.uiState.value.selected.contains(7))
    }

    @Test
    fun `a page that reports another idea keeps the notice of the one that was lost`() = runTest {
        // The retirement reads the page for the card the notice speaks of, not for any chosen card:
        // an idea the pair has held since an earlier visit says nothing about this tap.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returnsMany listOf(
                ApiResult.Success(listOf(rec, recBoard)),
                ApiResult.Success(listOf(rec, recBoard.copy(selected = true))),
            )
            coEvery { selectRecommendation("m1", 7) } returns ApiResult.Error(0, "Нет соединения")
        }
        val vm = viewModel(match)

        vm.select(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertNotNull(vm.uiState.value.selectError)
        assertTrue(vm.uiState.value.selected.contains(8))
        assertFalse(vm.uiState.value.selected.contains(7))
    }

    @Test
    fun `a later tap clears the notice of the idea that failed`() = runTest {
        // The notice is about one tap, and the card it names is back among the unchosen ones. A new
        // decision on this page ends the sentence about the old one instead of stacking two.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec, recBoard))
            coEvery { selectRecommendation("m1", 7) } returns ApiResult.Error(0, "Нет соединения")
            coEvery { selectRecommendation("m1", 8) } returns ApiResult.Success(Unit)
        }
        val vm = viewModel(match)

        vm.select(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertNotNull(vm.uiState.value.selectError)

        vm.select(8)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertNull(vm.uiState.value.selectError)
        assertEquals(setOf(8), vm.uiState.value.selected)
    }

    @Test
    fun `pushing an idea away hides it without deleting it`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec, recBoard))
            coEvery { declineRecommendation("m1", 7) } returns ApiResult.Success(Unit)
        }
        val vm = viewModel(match)

        vm.decline(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(setOf(7), vm.uiState.value.declined)
        // The idea stays on the page with its score and its reason: what a refusal edits is this
        // person's list, not the record, so the screen can offer it back.
        assertEquals(2, vm.uiState.value.items.size)
        assertNull(vm.uiState.value.declineError)
    }

    @Test
    fun `a refusal the server refused puts the card back and says so`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec))
            coEvery { declineRecommendation("m1", 7) } returns ApiResult.Error(0, "Нет соединения")
        }
        val vm = viewModel(match)

        vm.decline(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.declined.isEmpty())
        // Nothing half-succeeded here, so there is no debt to name — the card is back in the list
        // and the tap can simply be made again.
        assertEquals("Не удалось отклонить идею. Нет соединения", vm.uiState.value.declineError)
    }

    @Test
    fun `taking an idea back puts it in the list`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec, recBoard))
            coEvery { declineRecommendation("m1", 7) } returns ApiResult.Success(Unit)
            coEvery { restoreRecommendation("m1", 7) } returns ApiResult.Success(Unit)
        }
        val vm = viewModel(match)

        vm.decline(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertEquals(setOf(7), vm.uiState.value.declined)

        vm.restore(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.declined.isEmpty())
        coVerify(exactly = 1) { match.restoreRecommendation("m1", 7) }
    }

    @Test
    fun `a restore that failed leaves the idea where the person left it`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec.copy(declined = true)))
            coEvery { restoreRecommendation("m1", 7) } returns ApiResult.Error(0, "Нет соединения")
        }
        val vm = viewModel(match)

        assertEquals(setOf(7), vm.uiState.value.declined)

        vm.restore(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(setOf(7), vm.uiState.value.declined)
        assertEquals("Не удалось вернуть идею в подборку. Нет соединения", vm.uiState.value.declineError)
    }

    @Test
    fun `pushing away an idea that reached the pair keeps its mark`() = runTest {
        // The two answers a person can give the same card, both true at once: the idea did reach
        // the pair, and they have since decided they do not want it. Neither erases the other, so
        // the refused card still says the pair holds it.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec.copy(selected = true)))
            coEvery { declineRecommendation("m1", 7) } returns ApiResult.Success(Unit)
        }
        val vm = viewModel(match)

        vm.decline(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(setOf(7), vm.uiState.value.declined)
        assertEquals(setOf(7), vm.uiState.value.selected)
    }

    @Test
    fun `a page that reports the refusal carries it over to the next visit`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returnsMany listOf(
                ApiResult.Success(listOf(rec)),
                ApiResult.Success(listOf(rec.copy(declined = true))),
            )
        }
        val vm = viewModel(match)

        assertTrue(vm.uiState.value.declined.isEmpty())

        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(setOf(7), vm.uiState.value.declined)
    }

    @Test
    fun `a page that lands mid-refusal does not undo the tap`() = runTest {
        // The page was read before the write landed, so it cannot know the refusal. Left to its
        // own answer the reload would put the card back into the list and stay there, because a
        // successful write has nothing further to say.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } coAnswers {
                delay(50)
                ApiResult.Success(listOf(rec))
            }
            coEvery { declineRecommendation("m1", 7) } coAnswers {
                delay(200)
                ApiResult.Success(Unit)
            }
        }
        val vm = viewModel(match)

        vm.decline(7)
        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(setOf(7), vm.uiState.value.declined)
    }

    @Test
    fun `a page that lands mid-restore does not bury the idea again`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } coAnswers {
                delay(50)
                ApiResult.Success(listOf(rec.copy(declined = true)))
            }
            coEvery { restoreRecommendation("m1", 7) } coAnswers {
                delay(200)
                ApiResult.Success(Unit)
            }
        }
        val vm = viewModel(match)

        assertEquals(setOf(7), vm.uiState.value.declined)

        vm.restore(7)
        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.declined.isEmpty())
    }

    // ---------- Согласование времени ----------

    private val offeredByMe = "2026-10-17T19:00+03:00"
    private val offeredByPartner = "2026-10-18T20:00+03:00"
    private val movedHour = "2026-10-19T21:00+03:00"

    /** A page whose idea is already the pair's plan, which is the only state that arranges an hour. */
    private fun timeRepo(
        cards: List<Recommendation>,
        offer: ApiResult<Unit> = ApiResult.Success(Unit),
        accept: ApiResult<Unit> = ApiResult.Success(Unit),
    ) = mockk<MatchRepository> {
        coEvery { recommendations("m1") } returns ApiResult.Success(cards)
        coEvery { proposeMeetingTime("m1", any(), any()) } returns offer
        coEvery { acceptMeetingTime("m1", any(), any()) } returns accept
    }

    @Test
    fun `an hour named for an idea in the chat stays named on the card`() = runTest {
        val match = timeRepo(listOf(rec.copy(selected = true)))
        val vm = viewModel(match)

        vm.proposeTime(7, offeredByMe)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify { match.proposeMeetingTime("m1", 7, offeredByMe) }
        assertEquals(offeredByMe, vm.uiState.value.myOffers[7])
        assertTrue(vm.uiState.value.timeErrors.isEmpty())
    }

    @Test
    fun `an hour the server refused leaves nothing offered and says which tap failed`() = runTest {
        val match = timeRepo(listOf(rec.copy(selected = true)), offer = ApiResult.Error(0, "Нет соединения"))
        val vm = viewModel(match)

        vm.proposeTime(7, offeredByMe)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.myOffers.isEmpty())
        assertEquals("Не удалось предложить время. Нет соединения", vm.uiState.value.timeErrors[7])
    }

    @Test
    fun `a moved hour that was refused stands where the older hour stood`() = runTest {
        // The card named one moment, then this visit tried to move it and was refused. The offer the
        // pair can read is still the first one, so a rollback to nothing would deny the person what
        // the card actually holds.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec.copy(selected = true)))
            coEvery { proposeMeetingTime("m1", 7, offeredByMe) } returns ApiResult.Success(Unit)
            coEvery { proposeMeetingTime("m1", 7, movedHour) } returns ApiResult.Error(0, "Нет соединения")
        }
        val vm = viewModel(match)

        vm.proposeTime(7, offeredByMe)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.proposeTime(7, movedHour)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(offeredByMe, vm.uiState.value.myOffers[7])
        assertNotNull(vm.uiState.value.timeErrors[7])
    }

    @Test
    fun `the partner's hour is agreed to as it was read`() = runTest {
        val match = timeRepo(listOf(rec.copy(selected = true, partnerMeetingTime = offeredByPartner)))
        val vm = viewModel(match)

        vm.acceptTime(7, offeredByPartner)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify { match.acceptMeetingTime("m1", 7, offeredByPartner) }
        assertEquals(offeredByPartner, vm.uiState.value.agreedMoments[7])
    }

    @Test
    fun `tapping подходит twice confirms the hour once`() = runTest {
        val match = timeRepo(listOf(rec.copy(partnerMeetingTime = offeredByPartner)))
        val vm = viewModel(match)

        vm.acceptTime(7, offeredByPartner)
        vm.acceptTime(7, offeredByPartner)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { match.acceptMeetingTime(any(), any(), any()) }
    }

    @Test
    fun `an agreement the server refused does not claim a plan`() = runTest {
        val match = timeRepo(
            listOf(rec.copy(partnerMeetingTime = offeredByPartner)),
            accept = ApiResult.Error(0, "Партнёр уже предложил другое время."),
        )
        val vm = viewModel(match)

        vm.acceptTime(7, offeredByPartner)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.agreedMoments.isEmpty())
        assertTrue(vm.uiState.value.timeErrors[7]!!.startsWith("Не удалось подтвердить время."))
    }

    @Test
    fun `a page that reports the plan retires the notice of the refused agreement`() = runTest {
        // The answer can be lost while the write still lands, so the next page is the fact that ends
        // the doubt: the plan is on the pair, and there is nothing left to confirm.
        val withOffer = rec.copy(selected = true, partnerMeetingTime = offeredByPartner)
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returnsMany listOf(
                ApiResult.Success(listOf(withOffer)),
                ApiResult.Success(listOf(withOffer.copy(agreedTime = offeredByPartner))),
            )
            coEvery { proposeMeetingTime(any(), any(), any()) } returns ApiResult.Success(Unit)
            coEvery { acceptMeetingTime("m1", 7, offeredByPartner) } returns ApiResult.Error(0, "Нет соединения")
        }
        val vm = viewModel(match)

        vm.acceptTime(7, offeredByPartner)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertNotNull(vm.uiState.value.timeErrors[7])

        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.timeErrors.isEmpty())
        assertEquals(offeredByPartner, vm.uiState.value.agreedMoments[7])
    }

    @Test
    fun `a page that lands mid-offer does not undo the hour this person named`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } coAnswers {
                delay(50)
                ApiResult.Success(listOf(rec.copy(selected = true)))
            }
            coEvery { proposeMeetingTime("m1", 7, offeredByMe) } coAnswers {
                delay(200)
                ApiResult.Success(Unit)
            }
            coEvery { acceptMeetingTime(any(), any(), any()) } returns ApiResult.Success(Unit)
        }
        val vm = viewModel(match)

        vm.proposeTime(7, offeredByMe)
        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(offeredByMe, vm.uiState.value.myOffers[7])
    }

    @Test
    fun `a refused hour on one idea is not buried by a plan on another`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(
                listOf(
                    rec.copy(selected = true),
                    recBoard.copy(selected = true, partnerMeetingTime = offeredByPartner),
                ),
            )
            coEvery { acceptMeetingTime("m1", 8, offeredByPartner) } returns ApiResult.Success(Unit)
            coEvery { proposeMeetingTime("m1", 7, offeredByMe) } returns ApiResult.Error(0, "Нет соединения")
        }
        val vm = viewModel(match)

        vm.proposeTime(7, offeredByMe)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.acceptTime(8, offeredByPartner)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The second tap answered for its own card only: the hour the server refused for кино is
        // still missing and still has to be named where it was refused.
        assertNotNull(vm.uiState.value.timeErrors[7])
        assertEquals(offeredByPartner, vm.uiState.value.agreedMoments[8])
    }

    @Test
    fun `an hour named on one card is not read as the plan of another`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec.copy(selected = true), recBoard))
            coEvery { proposeMeetingTime("m1", 7, offeredByMe) } returns ApiResult.Success(Unit)
        }
        val vm = viewModel(match)

        vm.proposeTime(7, offeredByMe)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(offeredByMe, vm.uiState.value.myOffers[7])
        assertNull(vm.uiState.value.myOffers[8])
        assertTrue(vm.uiState.value.agreedMoments.isEmpty())
    }
}
