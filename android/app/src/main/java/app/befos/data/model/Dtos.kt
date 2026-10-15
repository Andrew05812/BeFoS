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
    // How the server puts this question: `scale` means the ordered options below are better set
    // with a thumb than tapped as cards. The default is what a response from before the field
    // actually says — a stack of cards, which is the shape every question has always had.
    val kind: String = "choice",
    val options: List<OptionDto> = emptyList(),
    // The option this person's stored answer stands on, null where the server holds none. A
    // response from before the field simply carries no marks, which is what it actually said.
    @SerialName("selected_option_id") val selectedOptionId: Int? = null,
)

@Serializable
data class CategoryProgressDto(
    val key: String,
    val label: String,
    val total: Int,
    val answered: Int,
)

@Serializable
data class TestListDto(
    val questions: List<QuestionDto> = emptyList(),
    val total: Int = 0,
    val answered: Int = 0,
    val categories: List<CategoryProgressDto> = emptyList(),
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
    // The sections behind those totals. A screen that has to name the empty part of the test asks
    // this route rather than the catalogue, because the answer costs one row per section instead of
    // every question text and every option.
    val categories: List<CategoryProgressDto> = emptyList(),
)

@Serializable
data class CategoryScoreDto(
    val category: String,
    val label: String,
    val score: Int,
    val weight: Double = 0.0,
    // False means the engine had nothing to compare this band on and fell back to its neutral
    // half. Defaulted to true so a response from before the field stays readable; a missing flag
    // then reads as measured, which is what the older wire actually promised.
    @SerialName("has_data") val hasData: Boolean = true,
)

@Serializable
data class TraitAxisDto(
    val category: String = "",
    val trait: String = "",
    val label: String = "",
    val value: Double = 0.0,
    val side: String = "",
)

@Serializable
data class TestResultDto(
    val categories: List<CategoryScoreDto> = emptyList(),
    // The positions the band percents are averaged from. A response from before the field simply
    // carries none, and the screen then shows the bands it has instead of inventing axes.
    val axes: List<TraitAxisDto> = emptyList(),
    @SerialName("completed_at") val completedAt: String? = null,
)

/**
 * The same profile read back from the server long after the evening it was scored.
 *
 * `updated_at` is kept as text: the moment belongs to the engine's clock, and turning it into a
 * date here would put the device's timezone in front of a value the person is being shown as the
 * server's own. Null is the profile the engine has never rebuilt, and the screen then says nothing
 * about when it changed rather than guessing a moment it was never given.
 */
@Serializable
data class TestProfileDto(
    val categories: List<CategoryScoreDto> = emptyList(),
    val axes: List<TraitAxisDto> = emptyList(),
    @SerialName("updated_at") val updatedAt: String? = null,
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

// ---------- Compatibility Universe ----------
@Serializable
data class UniverseNodeDto(
    val key: String = "",
    val label: String = "",
    @SerialName("a_value") val aValue: Double? = null,
    @SerialName("b_value") val bValue: Double? = null,
    @SerialName("has_data") val hasData: Boolean = false,
    val connection: String = "unknown",
    val evidence: String = "",
    val confidence: Int = 0,
    val suggestion: String = "",
    val questions: List<String> = emptyList(),
)

@Serializable
data class UniverseLayerDto(
    val category: String = "",
    val label: String = "",
    val score: Int = 0,
    val weight: Double = 0.0,
    @SerialName("has_data") val hasData: Boolean = false,
    val coverage: Double = 0.0,
    val confidence: Int = 0,
    val nodes: List<UniverseNodeDto> = emptyList(),
)

@Serializable
data class UniverseDto(
    val overall: Int,
    @SerialName("engine_version") val engineVersion: Int = 1,
    @SerialName("a_user_id") val aUserId: String = "",
    @SerialName("b_user_id") val bUserId: String = "",
    val layers: List<UniverseLayerDto> = emptyList(),
    val story: List<String> = emptyList(),
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
/**
 * What the server names as the plan a conversation line is about.
 *
 * Absent on an ordinary sentence, and its members are nullable on purpose: the card has to be able
 * to say «место не договорилось» rather than invent one, so a missing part arrives as missing
 * instead of as a placeholder the screen would have to guess the meaning of.
 */
@Serializable
data class MessagePlanDto(
    @SerialName("activity_id") val activityId: Int? = null,
    @SerialName("activity_title") val activityTitle: String? = null,
    // The moment the pair agreed to, in the ISO form the backend stamps — a plan is read as an
    // instant, not as the server's clock, so the card shows it in the device's own zone.
    @SerialName("when") val whenIso: String? = null,
    @SerialName("is_latest") val isLatest: Boolean = false,
)

@Serializable
data class MessageDto(
    val id: String,
    @SerialName("match_id") val matchId: String,
    @SerialName("sender_id") val senderId: String,
    val body: String,
    @SerialName("created_at") val createdAt: String = "",
    @SerialName("is_read") val isRead: Boolean = false,
    @SerialName("is_own") val isOwn: Boolean = false,
    // `text` for a sentence somebody typed; `plan_agreed` / `plan_voided` for what the pair's
    // agreement did to the conversation. Defaulted, so a build that predates the journal still
    // reads an older server's answers as the sentences they were.
    val kind: String = "text",
    val plan: MessagePlanDto? = null,
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
    // Whether this person already proposed this card to this pair, as the page reports it.
    val selected: Boolean = false,
    // Whether the other half of the pair did. The idea it marks is already readable in the pair's
    // chat, so naming it to this reader reveals nothing the pair does not already have.
    @SerialName("partner_selected") val partnerSelected: Boolean = false,
    // Whether this person pushed the card away. Never answered for the other half: a proposal is a
    // message the pair received, a refusal is one person editing their own list.
    val declined: Boolean = false,
    // The hours of this card, as ISO text with an offset. Kept as text rather than parsed here:
    // agreeing to an offer sends back exactly the string the person read, and a value parsed and
    // re-printed on the way could answer a moment nobody offered.
    @SerialName("my_meeting_time") val myMeetingTime: String? = null,
    @SerialName("partner_meeting_time") val partnerMeetingTime: String? = null,
    @SerialName("i_accepted_time") val iAcceptedTime: String? = null,
    @SerialName("agreed_time") val agreedTime: String? = null,
)

@Serializable
data class RecommendationListDto(
    @SerialName("match_id") val matchId: String = "",
    val recommendations: List<RecommendationDto> = emptyList(),
)

/** The moment this person names for a card, or agrees to. One field because one question is asked. */
@Serializable
data class MeetingTimeRequest(
    // The API calls this `when`, which is a Kotlin keyword, so the property is named for what it
    // holds and the wire name is pinned instead.
    @SerialName("when") val whenIso: String,
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
