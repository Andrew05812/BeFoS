package app.befos.domain.model

data class Interest(
    val slug: String,
    val name: String,
    val category: String,
)

data class Profile(
    val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    val gender: String,
    val about: String?,
    val datingGoal: String,
    val photoUrls: List<String>,
    val interests: List<Interest>,
    val lifestyle: Map<String, String>,
    val ageMin: Int,
    val ageMax: Int,
    val genderPreference: List<String>,
    val isHidden: Boolean = false,
) {
    val primaryPhoto: String? get() = photoUrls.firstOrNull()
}

data class Question(
    val id: Int,
    val category: String,
    val trait: String,
    val text: String,
    val options: List<Option>,
)

data class Option(
    val id: Int,
    val text: String,
)

data class TestProgress(
    val answered: Int,
    val total: Int,
    val percent: Int,
    val remaining: Int,
    val completed: Boolean,
)

data class CategoryScore(
    val category: String,
    val label: String,
    val score: Int,
    val weight: Double,
    val hasData: Boolean = true,
)

data class Explanation(
    val category: String,
    val label: String,
    val text: String,
    val score: Double,
)

data class Compatibility(
    val overall: Int,
    val categories: List<CategoryScore>,
    val strengths: List<Explanation>,
    val differences: List<Explanation>,
    val sharedInterests: List<String>,
)

/**
 * How two answers relate. `UNKNOWN` is not a weak match: it is the server saying there was
 * nothing to compare, and the map must draw it as an absence rather than as a meeting.
 */
enum class Connection {
    HARMONY,
    COMPLEMENTARITY,
    DISCUSSION,
    UNKNOWN,
    ;

    companion object {
        fun fromJson(raw: String): Connection =
            values().firstOrNull { it.name.equals(raw, ignoreCase = true) } ?: UNKNOWN
    }
}

data class UniverseNode(
    val key: String,
    val label: String,
    val aValue: Double?,
    val bValue: Double?,
    val hasData: Boolean,
    val connection: Connection,
    val evidence: String,
    val confidence: Int,
    val suggestion: String,
    val questions: List<String>,
)

data class UniverseLayer(
    val category: String,
    val label: String,
    val score: Int,
    val weight: Double,
    val hasData: Boolean,
    val coverage: Double,
    val confidence: Int,
    val nodes: List<UniverseNode>,
)

data class Universe(
    val overall: Int,
    val engineVersion: Int,
    val aUserId: String,
    val bUserId: String,
    val layers: List<UniverseLayer>,
    /**
     * The same map retold in aggregate sentences the pair can send outside the app. Written by the
     * engine from band percents and counts only — no axis label, no answer — so the reading that
     * travels is the one reading that carries nothing personal.
     */
    val story: List<String>,
)

data class DiscoveryCard(
    val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    val about: String?,
    val datingGoal: String,
    val photoUrl: String?,
    val interests: List<String>,
    val compatibility: Int,
    val sharedInterestsCount: Int,
    val highlight: String? = null,
)

/**
 * One page of the viewer's deck. The cursor is where the next page continues from, and
 * only the backend can know it: a card leaves the deck the moment it is swiped, so a
 * position would point at a different person on the next request.
 */
data class DiscoveryPage(
    val cards: List<DiscoveryCard>,
    val nextCursor: String?,
    val hasMore: Boolean,
)

data class PublicProfile(
    val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    val about: String?,
    val datingGoal: String,
    val gender: String,
    val interests: List<String>,
    val photoUrls: List<String>,
    val compatibility: Int,
    val categories: List<CategoryScore>,
    val sharedInterests: List<String>,
)

data class MatchSummary(
    val matchId: String,
    val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    val photoUrl: String?,
    val compatibility: Int,
    val lastMessage: String?,
    val lastMessageAt: String?,
    val unread: Int,
)

data class Message(
    val id: String,
    val matchId: String,
    val senderId: String,
    val body: String,
    val createdAt: String,
    val isRead: Boolean,
    val isOwn: Boolean,
)

data class Activity(
    val id: Int,
    val slug: String,
    val title: String,
    val description: String?,
    val category: String,
)

data class Recommendation(
    val activity: Activity,
    val score: Int,
    val position: Int,
    val reasons: List<String>,
    val selected: Boolean,
    // What the other half of the pair chose. The stored page is shared by both of them, so without
    // this the pair's screen can only ever show one voice.
    val partnerSelected: Boolean,
    // Whether this person pushed the card away. Never answered for the other half: a proposal is a
    // message the pair received, a refusal is one person editing their own list.
    val declined: Boolean,
    // The hour this person named for the card, and the hour the other half named. ISO text with an
    // offset, kept as text: agreeing sends back exactly the string the person read.
    val myMeetingTime: String?,
    val partnerMeetingTime: String?,
    // An hour this person agreed to that the partner has since moved. It is not a plan, and it is
    // not nothing either: the card says the agreement happened and that its moment is no longer the
    // one being offered.
    val iAcceptedTime: String?,
    // The moment both halves hold: null until one row's agreement equals the other row's offer.
    val agreedTime: String?,
)

data class LikeOutcome(
    val matched: Boolean,
    val matchId: String?,
    val compatibility: Int?,
)

data class OnboardingData(
    val name: String,
    val birthDate: String,
    val city: String,
    val gender: String,
    val about: String?,
    val datingGoal: String,
    val interests: List<String>,
    val lifestyle: Map<String, String>,
    val ageMin: Int,
    val ageMax: Int,
    val genderPreference: List<String>,
)

data class ProfileUpdateData(
    val name: String? = null,
    val city: String? = null,
    val about: String? = null,
    val datingGoal: String? = null,
    val gender: String? = null,
    val birthDate: String? = null,
    val interests: List<String>? = null,
    val lifestyle: Map<String, String>? = null,
    val ageMin: Int? = null,
    val ageMax: Int? = null,
    val genderPreference: List<String>? = null,
    val isHidden: Boolean? = null,
)
