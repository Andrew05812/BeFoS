package app.befos.presentation.recommendations

import app.befos.MainDispatcherRule
import app.befos.core.network.ApiResult
import app.befos.domain.model.Activity
import app.befos.domain.model.Message
import app.befos.domain.model.Recommendation
import app.befos.domain.repository.ChatRepository
import app.befos.domain.repository.MatchRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
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

    private val proposal = Message(
        id = "p1", matchId = "m1", senderId = "me", body = "Идея для нас: Поход в кино. Что скажете?",
        createdAt = "2026-01-01T00:00:00", isRead = false, isOwn = true,
    )

    private fun matchRepo() = mockk<MatchRepository> {
        coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec))
        coEvery { selectRecommendation("m1", 7) } returns ApiResult.Success(Unit)
    }

    private fun chatRepo(result: ApiResult<Message> = ApiResult.Success(proposal)) = mockk<ChatRepository> {
        coEvery { send("m1", any(), any()) } returns result
    }

    private fun viewModel(
        match: MatchRepository = matchRepo(),
        chat: ChatRepository = chatRepo(),
    ): RecommendationsViewModel {
        val vm = RecommendationsViewModel(match, chat, "m1")
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        return vm
    }

    @Test
    fun `proposal reaches the chat before the choice is recorded`() = runTest {
        val match = matchRepo()
        val chat = chatRepo()
        val vm = viewModel(match, chat)

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify { chat.send("m1", "Идея для нас: Поход в кино. Что скажете?", any()) }
        coVerify { match.selectRecommendation("m1", 7) }
        assertTrue(vm.uiState.value.selected.contains(7))
        assertNull(vm.uiState.value.selectError)
    }

    @Test
    fun `failed proposal rolls back and never records a choice`() = runTest {
        val match = matchRepo()
        val chat = chatRepo(ApiResult.Error(0, "Нет соединения"))
        val vm = viewModel(match, chat)

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.selected.isEmpty())
        assertEquals("Не удалось отправить предложение. Нет соединения", vm.uiState.value.selectError)
        assertTrue(vm.uiState.value.unsavedChoices.isEmpty())
        coVerify(exactly = 0) { match.selectRecommendation(any(), any()) }
    }

    @Test
    fun `tapping the same idea twice sends it once`() = runTest {
        val chat = chatRepo()
        val vm = viewModel(chat = chat)

        vm.select(7, cinema.title)
        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 1) { chat.send(any(), any(), any()) }
    }

    @Test
    fun `a proposal tap that got no answer is retried under the same name`() = runTest {
        val names = mutableListOf<String?>()
        val chat = mockk<ChatRepository> {
            coEvery { send("m1", any(), captureNullable(names)) } returnsMany listOf(
                ApiResult.Error(-1, "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."),
                ApiResult.Success(proposal),
            )
        }
        val vm = viewModel(chat = chat)

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(2, names.size)
        assertEquals(1, names.distinct().size)
        assertTrue(names.first() != null)
    }

    @Test
    fun `a card the page reports as proposed opens proposed and sends nothing on a tap`() = runTest {
        // The state a second visit to the tab starts from: the choice this person recorded for
        // this pair comes back on the page, so the tab has to be opened before the mark exists.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec.copy(selected = true)))
        }
        val chat = chatRepo()
        val vm = viewModel(match, chat)

        assertTrue(vm.uiState.value.selected.contains(7))

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify(exactly = 0) { chat.send(any(), any(), any()) }
    }

    @Test
    fun `a choice the server refused to record is named instead of silenced`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec))
            coEvery { selectRecommendation("m1", 7) } returns ApiResult.Error(0, "Нет соединения")
        }
        val vm = viewModel(match, chatRepo())

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // The idea is readable in chat, so the card keeps its mark; what the person has to be
        // told is that the pair's own record of it did not survive the request.
        assertNotNull(vm.uiState.value.selectError)
        assertTrue(vm.uiState.value.selectError!!.contains("чат"))
        assertTrue(vm.uiState.value.selected.contains(7))
        assertEquals(setOf(7), vm.uiState.value.unsavedChoices)
    }

    @Test
    fun `a refused record is retried as a record and never as a second message`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec))
            coEvery { selectRecommendation("m1", 7) } returns ApiResult.Error(0, "Нет соединения") andThen
                ApiResult.Success(Unit)
        }
        val chat = chatRepo()
        val vm = viewModel(match, chat)

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertNotNull(vm.uiState.value.selectError)

        vm.retryRecords()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertNull(vm.uiState.value.selectError)
        assertTrue(vm.uiState.value.unsavedChoices.isEmpty())
        coVerify(exactly = 1) { chat.send(any(), any(), any()) }
        coVerify(exactly = 2) { match.selectRecommendation("m1", 7) }
    }

    @Test
    fun `a record the server refuses twice stays named after the second refusal`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec))
            coEvery { selectRecommendation("m1", 7) } returns ApiResult.Error(0, "Нет соединения")
        }
        val vm = viewModel(match, chatRepo())

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.retryRecords()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(setOf(7), vm.uiState.value.unsavedChoices)
        assertEquals("Идея отправлена в чат, но отметить её в паре не удалось. Нет соединения", vm.uiState.value.selectError)
    }

    @Test
    fun `a page that reports the mark retires the notice`() = runTest {
        // The record can reach the pair even though its answer was lost, so the next page is
        // the fact that ends the doubt: the mark came back, nothing has to be retried.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returnsMany listOf(
                ApiResult.Success(listOf(rec)),
                ApiResult.Success(listOf(rec.copy(selected = true))),
            )
            coEvery { selectRecommendation("m1", 7) } returns ApiResult.Error(0, "Нет соединения")
        }
        val vm = viewModel(match, chatRepo())

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        assertNotNull(vm.uiState.value.selectError)

        vm.load()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.unsavedChoices.isEmpty())
        assertNull(vm.uiState.value.selectError)
        assertTrue(vm.uiState.value.selected.contains(7))
    }

    @Test
    fun `a send failure never claims a missing record`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec))
            coEvery { selectRecommendation(any(), any()) } returns ApiResult.Success(Unit)
        }
        val vm = viewModel(match, chatRepo(ApiResult.Error(0, "Сервер недоступен")))

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.retryRecords()
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        // Nothing was recorded and nothing needs recording: the retry has no target here, so
        // the notice must stay about the message and must not offer to re-send a mark.
        assertEquals("Не удалось отправить предложение. Сервер недоступен", vm.uiState.value.selectError)
        coVerify(exactly = 0) { match.selectRecommendation(any(), any()) }
    }

    @Test
    fun `an idea the partner proposed is answered in chat instead of proposed again`() = runTest {
        // What the page now reports: the other half put this card into the pair's chat, so the
        // sentence this tap sends is an answer to it rather than a second copy of the proposal.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns
                ApiResult.Success(listOf(rec.copy(partnerSelected = true)))
            coEvery { selectRecommendation("m1", 7) } returns ApiResult.Success(Unit)
        }
        val chat = chatRepo()
        val vm = viewModel(match, chat)

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify { chat.send("m1", "Я тоже за: Поход в кино.", any()) }
        coVerify(exactly = 0) {
            chat.send("m1", "Идея для нас: Поход в кино. Что скажете?", any())
        }
        assertTrue(vm.uiState.value.selected.contains(7))
        assertNull(vm.uiState.value.selectError)
    }

    @Test
    fun `a second tap does not bury the notice of the idea still missing its mark`() = runTest {
        // The tap clears the notice of its own attempt, and a successful record of the second
        // idea says nothing about the first one: its mark is still missing and still has to show.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec, recBoard))
            coEvery { selectRecommendation("m1", 7) } returns ApiResult.Error(0, "Нет соединения")
            coEvery { selectRecommendation("m1", 8) } returns ApiResult.Success(Unit)
        }
        val vm = viewModel(match, chatRepo())

        vm.select(7, cinema.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()
        vm.select(8, boardGames.title)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(setOf(7), vm.uiState.value.unsavedChoices)
        assertTrue(vm.uiState.value.selectError!!.startsWith("Идея отправлена в чат"))
        assertTrue(vm.uiState.value.selected.containsAll(setOf(7, 8)))
    }

    @Test
    fun `pushing an idea away hides it without deleting it`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec, recBoard))
            coEvery { declineRecommendation("m1", 7) } returns ApiResult.Success(Unit)
        }
        val chat = chatRepo()
        val vm = viewModel(match, chat)

        vm.decline(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(setOf(7), vm.uiState.value.declined)
        // The idea stays on the page with its score and its reason: what a refusal edits is this
        // person's list, not the record, so the screen can offer it back.
        assertEquals(2, vm.uiState.value.items.size)
        assertNull(vm.uiState.value.declineError)
        coVerify(exactly = 0) { chat.send(any(), any(), any()) }
    }

    @Test
    fun `a refusal the server refused puts the card back and says so`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec))
            coEvery { declineRecommendation("m1", 7) } returns ApiResult.Error(0, "Нет соединения")
        }
        val vm = viewModel(match, chatRepo())

        vm.decline(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(vm.uiState.value.declined.isEmpty())
        // Nothing half-succeeded here: no message went to the chat, so there is no debt to retry —
        // the card is back in the list and the tap can simply be made again.
        assertEquals("Не удалось отклонить идею. Нет соединения", vm.uiState.value.declineError)
    }

    @Test
    fun `taking an idea back puts it in the list`() = runTest {
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec, recBoard))
            coEvery { declineRecommendation("m1", 7) } returns ApiResult.Success(Unit)
            coEvery { restoreRecommendation("m1", 7) } returns ApiResult.Success(Unit)
        }
        val vm = viewModel(match, chatRepo())

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
        val vm = viewModel(match, chatRepo())

        assertEquals(setOf(7), vm.uiState.value.declined)

        vm.restore(7)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(setOf(7), vm.uiState.value.declined)
        assertEquals("Не удалось вернуть идею в подборку. Нет соединения", vm.uiState.value.declineError)
    }

    @Test
    fun `pushing away an idea that went to chat keeps its mark`() = runTest {
        // The two answers a person can give the same card, both true at once: the idea did reach
        // the pair's chat, and they have since decided they do not want it. Neither erases the
        // other, so the refused card still says the chat holds it.
        val match = mockk<MatchRepository> {
            coEvery { recommendations("m1") } returns ApiResult.Success(listOf(rec.copy(selected = true)))
            coEvery { declineRecommendation("m1", 7) } returns ApiResult.Success(Unit)
        }
        val vm = viewModel(match, chatRepo())

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
        val vm = viewModel(match, chatRepo())

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
        val vm = viewModel(match, chatRepo())

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
        val vm = viewModel(match, chatRepo())

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

    /** A page whose idea is already in the chat, which is the only state that arranges an hour. */
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
        val vm = viewModel(match, chatRepo())

        vm.proposeTime(7, offeredByMe)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify { match.proposeMeetingTime("m1", 7, offeredByMe) }
        assertEquals(offeredByMe, vm.uiState.value.myOffers[7])
        assertTrue(vm.uiState.value.timeErrors.isEmpty())
    }

    @Test
    fun `an hour the server refused leaves nothing offered and says which tap failed`() = runTest {
        val match = timeRepo(listOf(rec.copy(selected = true)), offer = ApiResult.Error(0, "Нет соединения"))
        val vm = viewModel(match, chatRepo())

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
        val vm = viewModel(match, chatRepo())

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
        val vm = viewModel(match, chatRepo())

        vm.acceptTime(7, offeredByPartner)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        coVerify { match.acceptMeetingTime("m1", 7, offeredByPartner) }
        assertEquals(offeredByPartner, vm.uiState.value.agreedMoments[7])
    }

    @Test
    fun `tapping подходит twice confirms the hour once`() = runTest {
        val match = timeRepo(listOf(rec.copy(partnerMeetingTime = offeredByPartner)))
        val vm = viewModel(match, chatRepo())

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
        val vm = viewModel(match, chatRepo())

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
        val vm = viewModel(match, chatRepo())

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
        val vm = viewModel(match, chatRepo())

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
        val vm = viewModel(match, chatRepo())

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
        val vm = viewModel(match, chatRepo())

        vm.proposeTime(7, offeredByMe)
        mainRule.testDispatcher.scheduler.advanceUntilIdle()

        assertEquals(offeredByMe, vm.uiState.value.myOffers[7])
        assertNull(vm.uiState.value.myOffers[8])
        assertTrue(vm.uiState.value.agreedMoments.isEmpty())
    }
}
