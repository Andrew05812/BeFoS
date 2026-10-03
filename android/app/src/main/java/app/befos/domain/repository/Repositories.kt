package app.befos.domain.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.StoredAuth
import app.befos.domain.model.Compatibility
import app.befos.domain.model.DiscoveryCard
import app.befos.domain.model.Interest
import app.befos.domain.model.LikeOutcome
import app.befos.domain.model.MatchSummary
import app.befos.domain.model.Message
import app.befos.domain.model.OnboardingData
import app.befos.domain.model.Profile
import app.befos.domain.model.ProfileUpdateData
import app.befos.domain.model.PublicProfile
import app.befos.domain.model.Question
import app.befos.domain.model.Recommendation
import app.befos.domain.model.TestProgress
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
    suspend fun questions(): ApiResult<List<Question>>
    suspend fun progress(): ApiResult<TestProgress>
    suspend fun submitAnswers(answers: Map<Int, Int>): ApiResult<TestProgress>
    suspend fun complete(): ApiResult<List<app.befos.domain.model.CategoryScore>>
}

interface DiscoveryRepository {
    suspend fun feed(limit: Int, offset: Int): ApiResult<List<DiscoveryCard>>
    suspend fun like(userId: String): ApiResult<LikeOutcome>
    suspend fun pass(userId: String): ApiResult<Unit>
}

interface MatchRepository {
    suspend fun matches(): ApiResult<List<MatchSummary>>
    suspend fun partner(matchId: String): ApiResult<PublicProfile>
    suspend fun compatibility(matchId: String): ApiResult<Compatibility>
    suspend fun recommendations(matchId: String): ApiResult<List<Recommendation>>
    suspend fun selectRecommendation(matchId: String, activityId: Int): ApiResult<Unit>
}

interface ChatRepository {
    suspend fun history(matchId: String, beforeId: String? = null): ApiResult<List<Message>>
    suspend fun send(matchId: String, body: String): ApiResult<Message>
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
