package app.befos.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ---------- Auth ----------
@Serializable
data class UserBriefDto(
    val id: String,
    val email: String,
    @SerialName("is_active") val isActive: Boolean = true,
    @SerialName("created_at") val createdAt: String = "",
)

@Serializable
data class TokenPairDto(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("token_type") val tokenType: String = "bearer",
    @SerialName("expires_in") val expiresIn: Int = 0,
)

@Serializable
data class AuthResponseDto(
    val user: UserBriefDto,
    val tokens: TokenPairDto,
)

@Serializable
data class RegisterRequest(
    val email: String,
    val password: String,
    @SerialName("password_confirm") val passwordConfirm: String,
)

@Serializable
data class LoginRequest(
    val email: String,
    val password: String,
)

@Serializable
data class RefreshRequest(
    @SerialName("refresh_token") val refreshToken: String,
)

// ---------- Profile ----------
@Serializable
data class PhotoDto(
    val id: String,
    val url: String,
    @SerialName("is_primary") val isPrimary: Boolean = false,
    val position: Int = 0,
)

@Serializable
data class InterestDto(
    val slug: String,
    val name: String,
    val category: String = "",
)

@Serializable
data class InterestListDto(
    val interests: List<InterestDto> = emptyList(),
)

@Serializable
data class ProfileDto(
    @SerialName("user_id") val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    val gender: String = "",
    val about: String? = null,
    @SerialName("dating_goal") val datingGoal: String = "",
    val photos: List<PhotoDto> = emptyList(),
    val interests: List<InterestDto> = emptyList(),
    val lifestyle: Map<String, String> = emptyMap(),
    @SerialName("age_min") val ageMin: Int = 18,
    @SerialName("age_max") val ageMax: Int = 60,
    @SerialName("gender_preference") val genderPreference: List<String> = emptyList(),
    @SerialName("is_hidden") val isHidden: Boolean = false,
)

@Serializable
data class OnboardingRequest(
    val name: String,
    @SerialName("birth_date") val birthDate: String,
    val city: String,
    val gender: String,
    val about: String? = null,
    @SerialName("dating_goal") val datingGoal: String,
    val interests: List<String> = emptyList(),
    val lifestyle: Map<String, String> = emptyMap(),
    @SerialName("age_min") val ageMin: Int = 18,
    @SerialName("age_max") val ageMax: Int = 60,
    @SerialName("gender_preference") val genderPreference: List<String> = emptyList(),
)

@Serializable
data class ProfileUpdateRequest(
    val name: String? = null,
    val city: String? = null,
    val about: String? = null,
    @SerialName("dating_goal") val datingGoal: String? = null,
    val gender: String? = null,
    @SerialName("birth_date") val birthDate: String? = null,
    val interests: List<String>? = null,
    val lifestyle: Map<String, String>? = null,
    @SerialName("age_min") val ageMin: Int? = null,
    @SerialName("age_max") val ageMax: Int? = null,
    @SerialName("gender_preference") val genderPreference: List<String>? = null,
    @SerialName("is_hidden") val isHidden: Boolean? = null,
)

// ---------- Tests ----------
@Serializable
data class OptionDto(
    val id: Int,
    val text: String,
    val position: Int = 0,
)

@Serializable
data class QuestionDto(
    val id: Int,
    val category: String = "",
    val trait: String = "",
    val text: String,
    val position: Int = 0,
    val options: List<OptionDto> = emptyList(),
)

@Serializable
data class TestListDto(
    val questions: List<QuestionDto> = emptyList(),
    val total: Int = 0,
    val answered: Int = 0,
)

@Serializable
data class AnswerDto(
    @SerialName("question_id") val questionId: Int,
    @SerialName("option_id") val optionId: Int,
)

@Serializable
data class AnswersRequest(
    val answers: List<AnswerDto>,
)

@Serializable
data class ProgressDto(
    val answered: Int = 0,
    val total: Int = 0,
    val percent: Int = 0,
    val remaining: Int = 0,
    val completed: Boolean = false,
)

@Serializable
data class CategoryScoreDto(
    val category: String,
    val label: String,
    val score: Int,
    val weight: Double = 0.0,
)

@Serializable
data class TestResultDto(
    val categories: List<CategoryScoreDto> = emptyList(),
    @SerialName("completed_at") val completedAt: String? = null,
)

// ---------- Compatibility ----------
@Serializable
data class ExplanationItemDto(
    val category: String = "",
    val label: String = "",
    val text: String = "",
    val score: Double = 0.0,
)

@Serializable
data class CompatibilityDto(
    val overall: Int,
    @SerialName("engine_version") val engineVersion: Int = 1,
    val categories: List<CategoryScoreDto> = emptyList(),
    val strengths: List<ExplanationItemDto> = emptyList(),
    val differences: List<ExplanationItemDto> = emptyList(),
    @SerialName("shared_interests") val sharedInterests: List<String> = emptyList(),
)

// ---------- Discovery ----------
@Serializable
data class DiscoveryCardDto(
    @SerialName("user_id") val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    val about: String? = null,
    @SerialName("dating_goal") val datingGoal: String = "",
    @SerialName("photo_url") val photoUrl: String? = null,
    val interests: List<String> = emptyList(),
    val compatibility: Int = 0,
    @SerialName("shared_interests_count") val sharedInterestsCount: Int = 0,
    val highlight: String? = null,
)

/**
 * One page of the deck. `next_cursor` is the only way to ask for the next page: the deck
 * is ranked once on the server, and a position would name a different card after a swipe.
 */
@Serializable
data class DiscoveryPageDto(
    val items: List<DiscoveryCardDto> = emptyList(),
    @SerialName("next_cursor") val nextCursor: String? = null,
    @SerialName("has_more") val hasMore: Boolean = false,
)

@Serializable
data class LikeResponseDto(
    val liked: Boolean = false,
    val match: Boolean = false,
    @SerialName("match_id") val matchId: String? = null,
    val compatibility: Int? = null,
)

@Serializable
data class PassResponseDto(
    val passed: Boolean = false,
)

@Serializable
data class PublicProfileDto(
    @SerialName("user_id") val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    val about: String? = null,
    @SerialName("dating_goal") val datingGoal: String = "",
    val gender: String = "",
    val interests: List<String> = emptyList(),
    val photos: List<String> = emptyList(),
    val compatibility: Int = 0,
    val categories: List<CategoryScoreDto> = emptyList(),
    @SerialName("shared_interests") val sharedInterests: List<String> = emptyList(),
)

// ---------- Matches ----------
@Serializable
data class MatchSummaryDto(
    @SerialName("match_id") val matchId: String,
    @SerialName("user_id") val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    @SerialName("photo_url") val photoUrl: String? = null,
    val compatibility: Int = 0,
    @SerialName("last_message") val lastMessage: String? = null,
    @SerialName("last_message_at") val lastMessageAt: String? = null,
    val unread: Int = 0,
    @SerialName("created_at") val createdAt: String = "",
)

@Serializable
data class MatchListDto(
    val matches: List<MatchSummaryDto> = emptyList(),
)

@Serializable
data class MatchDetailDto(
    @SerialName("match_id") val matchId: String,
    val compatibility: Int = 0,
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("other_user") val otherUser: PublicProfileDto,
)

// ---------- Chat ----------
@Serializable
data class MessageDto(
    val id: String,
    @SerialName("match_id") val matchId: String,
    @SerialName("sender_id") val senderId: String,
    val body: String,
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("is_read") val isRead: Boolean = false,
    @SerialName("is_own") val isOwn: Boolean = false,
)

@Serializable
data class MessageRequest(
    val body: String,
    // The app's own name for this send. A POST whose answer never arrived is
    // indistinguishable from a POST that was refused, and the backend stores one message
    // per (match, sender, id), so retrying the same attempt cannot write it twice.
    @SerialName("client_msg_id") val clientMsgId: String? = null,
)

@Serializable
data class MessagePageDto(
    val messages: List<MessageDto> = emptyList(),
    @SerialName("has_more") val hasMore: Boolean = false,
)

// ---------- Recommendations ----------
@Serializable
data class ActivityDto(
    val id: Int,
    val slug: String = "",
    val title: String,
    val description: String? = null,
    val category: String = "",
    val energy: Double = 0.0,
    val social: Double = 0.0,
    val cost: Double = 0.0,
)

@Serializable
data class RecommendationDto(
    val activity: ActivityDto,
    val score: Int = 0,
    val position: Int = 0,
    val reasons: List<String> = emptyList(),
)

@Serializable
data class RecommendationListDto(
    @SerialName("match_id") val matchId: String = "",
    val recommendations: List<RecommendationDto> = emptyList(),
)

// ---------- Safety ----------
@Serializable
data class ReportRequest(
    val reason: String,
    val details: String? = null,
)

@Serializable
data class VisibilityRequest(
    val hidden: Boolean,
)

@Serializable
data class OkDto(
    val ok: Boolean = true,
)
