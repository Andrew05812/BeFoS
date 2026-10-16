package app.befos.domain.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.StoredAuth
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
}

interface ProfileRepository {
    suspend fun me(): ApiResult<Profile>
    suspend fun onboarding(data: OnboardingData): ApiResult<Profile>
    suspend fun update(data: ProfileUpdateData): ApiResult<Profile>
    suspend fun uploadPhoto(input: InputStream, contentType: String): ApiResult<Profile>
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

    /** Stand behind the idea — the same write as the tap on the pair's card, from another door. */
    suspend fun accept(planId: String): ApiResult<Unit>
    suspend fun decline(planId: String): ApiResult<Unit>
    suspend fun restoreDecline(planId: String): ApiResult<Unit>

    /** Name — or move — this person's hour, and agree to the one the other half named. */
    suspend fun offerHour(planId: String, whenIso: String): ApiResult<Unit>
    suspend fun confirmHour(planId: String, whenIso: String): ApiResult<Unit>

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
    suspend fun report(userId: String, reason: String, details: String?): ApiResult<Unit>
    suspend fun setVisibility(hidden: Boolean): ApiResult<Unit>
    suspend fun deleteAccount(): ApiResult<Unit>
}
