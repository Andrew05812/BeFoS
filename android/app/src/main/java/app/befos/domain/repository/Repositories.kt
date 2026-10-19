package app.befos.domain.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.StoredAuth
import app.befos.domain.model.BlockedUser
import app.befos.domain.model.Compatibility
import app.befos.domain.model.DiscoveryPage
import app.befos.domain.model.Interest
import app.befos.domain.model.LikeOutcome
import app.befos.domain.model.MatchSummary
import app.befos.domain.model.Message
import app.befos.domain.model.OnboardingData
import app.befos.domain.model.Plan
import app.befos.domain.model.Profile
import app.befos.domain.model.ProfileUpdateData
import app.befos.domain.model.PublicProfile
import app.befos.domain.model.Recommendation
import app.befos.domain.model.ReportDetail
import app.befos.domain.model.ReportsPage
import app.befos.domain.model.ReviewOutcome
import app.befos.domain.model.SessionsPage
import app.befos.domain.model.TestCatalog
import app.befos.domain.model.TestProfile
import app.befos.domain.model.TestProgress
import app.befos.domain.model.Universe
import kotlinx.coroutines.flow.Flow
import java.io.InputStream

sealed interface ChatEvent {
    data class IncomingMessage(val message: Message) : ChatEvent
    data class Typing(val userId: String, val typing: Boolean) : ChatEvent
    data class Read(val userId: String) : ChatEvent
    data class Presence(val userId: String, val online: Boolean) : ChatEvent
    data class Error(val message: String) : ChatEvent
    /** Live socket opened successfully. */
    data object Connected : ChatEvent
    /** Socket dropped; the repository will keep retrying with backoff. */
    data object Disconnected : ChatEvent
}

interface AuthRepository {
    val authState: Flow<StoredAuth?>
    suspend fun current(): StoredAuth?
    suspend fun lastEmail(): String?
    suspend fun register(email: String, password: String): ApiResult<String>
    suspend fun login(email: String, password: String): ApiResult<String>
    suspend fun logout()

    /**
     * Write a new word over the account's old one. A success means the device's own session is gone
     * with every other one the account holds, so the caller must not stay signed in afterwards.
     */
    suspend fun changePassword(
        oldPassword: String,
        newPassword: String,
        passwordConfirm: String,
    ): ApiResult<Unit>

    /**
     * The devices this account can still open a session on, newest first, with the answer about
     * whether the list stopped short.
     *
     * Nothing is passed and nothing is asked about another account: the session on the server says
     * whose list this is, so no screen can be talked into reading somebody else's devices.
     */
    suspend fun sessions(): ApiResult<SessionsPage>

    /**
     * End one of this account's own sessions by the id the list carried.
     *
     * A success says the row is cut, not that the device holding it knows yet: an access token already
     * signed stays usable until it expires on its own, which is why the caller has to drop its own
     * tokens when the row it named was this device's.
     */
    suspend fun endSession(sessionId: String): ApiResult<Unit>

    /**
     * End every session the account holds. This device's row is among them, so a success drops the
     * stored pair exactly as [changePassword] does — the server has revoked the session this device
     * stands on and will not answer for it again at the next refresh.
     */
    suspend fun endEverySession(): ApiResult<Unit>
}

interface ProfileRepository {
    suspend fun me(): ApiResult<Profile>
    suspend fun onboarding(data: OnboardingData): ApiResult<Profile>
    suspend fun update(data: ProfileUpdateData): ApiResult<Profile>
    suspend fun uploadPhoto(input: InputStream, contentType: String): ApiResult<Profile>
    /** Remove one photograph the person owns, by the number the server gave it. */
    suspend fun deletePhoto(photoId: String): ApiResult<Profile>
    /** Move one photograph to the head of the row, so it is the one readers are shown first. */
    suspend fun makePhotoPrimary(photoId: String): ApiResult<Profile>
    /** Write the whole row in the order named; a photograph left out of the list refuses the write. */
    suspend fun reorderPhotos(photoIds: List<String>): ApiResult<Profile>
    suspend fun interests(): ApiResult<List<Interest>>
    suspend fun publicProfile(userId: String): ApiResult<PublicProfile>
}

interface TestRepository {
    suspend fun catalog(): ApiResult<TestCatalog>
    suspend fun progress(): ApiResult<TestProgress>
    suspend fun submitAnswers(answers: Map<Int, Int>): ApiResult<TestProgress>
    suspend fun complete(): ApiResult<TestProfile>

    /** The stored profile, read without scoring anything: [complete] writes and refuses a short questionnaire. */
    suspend fun profile(): ApiResult<TestProfile>
}

interface DiscoveryRepository {
    suspend fun feed(limit: Int, cursor: String?): ApiResult<DiscoveryPage>
    suspend fun like(userId: String): ApiResult<LikeOutcome>
    suspend fun pass(userId: String): ApiResult<Unit>
}

interface MatchRepository {
    suspend fun matches(): ApiResult<List<MatchSummary>>
    suspend fun partner(matchId: String): ApiResult<PublicProfile>
    suspend fun compatibility(matchId: String): ApiResult<Compatibility>
    suspend fun universe(matchId: String): ApiResult<Universe>
    suspend fun recommendations(matchId: String): ApiResult<List<Recommendation>>
    suspend fun selectRecommendation(matchId: String, activityId: Int): ApiResult<Unit>
    suspend fun declineRecommendation(matchId: String, activityId: Int): ApiResult<Unit>
    suspend fun restoreRecommendation(matchId: String, activityId: Int): ApiResult<Unit>

    /** Name — or move — the hour this person would meet at for an idea the pair already has in chat. */
    suspend fun proposeMeetingTime(matchId: String, activityId: Int, whenIso: String): ApiResult<Unit>

    /** Agree to the hour the other half named, sending back exactly the instant that was read. */
    suspend fun acceptMeetingTime(matchId: String, activityId: Int, whenIso: String): ApiResult<Unit>

    /**
     * End the pair without blocking the person. The conversation and the pair's plans go with it,
     * and the two likes go too: one new tap from one person alone cannot bring the pair back.
     */
    suspend fun dissolve(matchId: String): ApiResult<Unit>
}

/**
 * The pair's arrangements, read and moved through the plan's own routes.
 *
 * Every call names the plan by its id and nothing else: who is asking, and whether that person is
 * one of the two the plan belongs to, is answered by the session on the server. A method here takes
 * no user id and sends none, so no screen can be talked into acting for somebody else.
 */
interface PlanRepository {
    suspend fun plans(matchId: String): ApiResult<List<Plan>>

    /**
     * One plan by its own id, for the device that holds an alarm about it rather than a page of it.
     *
     * A reminder is armed by the plans page and spoken much later, and the pair can move that hour in
     * between; this is the read the waking device compares its own sentence against.
     */
    suspend fun plan(planId: String): ApiResult<Plan>

    /**
     * The plan's own chronology, as the pair's conversation holds it.
     *
     * These are the same journal lines the chat draws, read through the plan rather than through the
     * thread: the server writes one line per state the pair moved through, with its kind, the person
     * whose tap produced it, and both edges of whatever field moved. No screen keeps a second copy of
     * that record, so a history cannot disagree with the chat about a tap whose answer was lost.
     */
    suspend fun history(planId: String): ApiResult<List<Message>>

    /** Stand behind the idea — the same write as the tap on the pair's card, from another door. */
    suspend fun accept(planId: String): ApiResult<Unit>
    suspend fun decline(planId: String): ApiResult<Unit>
    suspend fun restoreDecline(planId: String): ApiResult<Unit>

    /** Name — or move — this person's hour, and agree to the one the other half named. */
    suspend fun offerHour(planId: String, whenIso: String): ApiResult<Unit>
    suspend fun confirmHour(planId: String, whenIso: String): ApiResult<Unit>

    /**
     * Write the pair's own words about the arrangement — its place and their note — or take one of
     * them back. Both halves hold the same two lines, so either may write them; the clearing flags
     * exist because an omitted field means «не трогать» and only a said erasure removes a place.
     */
    suspend fun editWords(
        planId: String,
        place: String?,
        note: String?,
        clearPlace: Boolean,
        clearNote: Boolean,
    ): ApiResult<Unit>

    suspend fun cancel(planId: String): ApiResult<Unit>
    suspend fun restore(planId: String): ApiResult<Unit>

    /** This person's own word that the meeting happened; the plan is «состоялось» only for both. */
    suspend fun markAttended(planId: String): ApiResult<Unit>
    suspend fun undoAttended(planId: String): ApiResult<Unit>
}

interface ChatRepository {
    suspend fun history(matchId: String, beforeId: String? = null): ApiResult<List<Message>>
    suspend fun send(matchId: String, body: String, clientMsgId: String?): ApiResult<Message>
    suspend fun markRead(matchId: String): ApiResult<Unit>
    fun socket(matchId: String): Flow<ChatEvent>
    suspend fun sendTyping(matchId: String, typing: Boolean)
}

interface SafetyRepository {
    suspend fun block(userId: String): ApiResult<Unit>

    /**
     * Takes one of this account's own blocks back. The answer is the list that stands after the
     * write, because the screen has to paint what the server holds rather than what the tap named.
     */
    suspend fun unblock(userId: String): ApiResult<List<BlockedUser>>
    suspend fun blockedUsers(): ApiResult<List<BlockedUser>>

    suspend fun report(userId: String, reason: String, details: String?): ApiResult<Unit>
    suspend fun setVisibility(hidden: Boolean): ApiResult<Unit>
    suspend fun deleteAccount(): ApiResult<Unit>
}

/**
 * The moderation queue, read and decided through the three routes stage 102 put behind
 * `get_moderator`.
 *
 * None of these three answers is a permission check the client can substitute for: the role is read
 * off the account row on every request, so an account that reached this screen without holding it
 * gets 403 from the server rather than a queue. What the screen does with that 403 is say so out
 * loud, not pretend the row it asked about does not exist.
 */
interface ModerationRepository {
    /** One page of the queue, oldest complaint first; a null status asks for every status. */
    suspend fun page(status: String?, afterId: String?): ApiResult<ReportsPage>

    /** One complaint with the history of how it was decided and the statuses still open to it. */
    suspend fun detail(reportId: String): ApiResult<ReportDetail>

    /**
     * Moves one complaint to one status.
     *
     * The answer is the status the row holds after the write's own commit, which is the status that
     * was asked for only when the transition was still legal at the moment the row was locked — a
     * second moderator deciding the same complaint in the same second is the case this returns
     * rather than the one it prevents.
     */
    suspend fun review(reportId: String, status: String, comment: String?): ApiResult<ReviewOutcome>
}
