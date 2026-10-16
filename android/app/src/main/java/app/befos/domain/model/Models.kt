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
    // The option the server's stored answer stands on, null where it holds none. The screen marks
    // that card and the flow starts on the first question that has no mark.
    val selectedOptionId: Int? = null,
    // How the question is put to the person. `scale` is the same ordered options drawn as a slider;
    // anything else — including a kind a later server invents — stays the stack of cards, because
    // cards are the one shape every option set can be answered with.
    val kind: String = KIND_CHOICE,
) {
    val isScale: Boolean get() = kind == KIND_SCALE
}

const val KIND_CHOICE = "choice"
const val KIND_SCALE = "scale"

data class CategoryProgress(
    val key: String,
    val label: String,
    val total: Int,
    val answered: Int,
)

// What the test route answers in one call: the catalogue with the person's own marks on it, and
// how far each of its categories has come. Kept together because the screen needs both to say
// where the person is — the question they stopped on comes from the marks, the section it belongs
// to comes from the counts.
data class TestCatalog(
    val questions: List<Question>,
    val categories: List<CategoryProgress>,
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
    // The same sections the catalogue route prints, so a screen can name the part of the test that
    // is still empty without carrying the question texts to find out.
    val categories: List<CategoryProgress> = emptyList(),
)

data class CategoryScore(
    val category: String,
    val label: String,
    val score: Int,
    val weight: Double,
    val hasData: Boolean = true,
)

/**
 * One axis of the questionnaire, measured from the person's own answers. The band percents are the
 * averages of these, so an axis is the position a band was built from — and the word the engine
 * reads out of it, quoted from the server rather than guessed from the number here.
 */
data class TraitAxis(
    val category: String,
    val trait: String,
    val label: String,
    val value: Double,
    val side: String,
)

/**
 * The bands and the axes behind them — what the questionnaire says about the person.
 *
 * Both routes that hand it over answer with the same two lists, the one that scores the answers on
 * the finished evening and the one that reads that scoring back weeks later, so this model carries
 * neither a source flag nor a second shape. `updatedAt` belongs to the reading: a profile opened
 * long after it was built has to say when it last spoke from, and null is the answer of a profile
 * the engine has never rebuilt at all.
 */
data class TestProfile(
    val categories: List<CategoryScore> = emptyList(),
    val axes: List<TraitAxis> = emptyList(),
    val updatedAt: String? = null,
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

/**
 * The kinds a conversation line arrives with.
 *
 * `text` is a sentence somebody typed; the rest are what the pair's plan wrote into the thread, one
 * kind per move — an idea put to the pair, an hour agreed, a plan brought to an end. The screen has
 * to tell them apart because a plan is not anybody's bubble, and because only `plan_agreed` and
 * `plan_changed` hold an hour the pair agreed to: a card that read any of the others as a standing
 * agreement would show the pair a promise they never made. A kind this build does not know is still
 * drawn as a card, and says on its face that this version cannot read it — a newer server cannot buy
 * a blank space, or worse a live agreement, on a screen it cannot reach.
 */
object MessageKinds {
    const val TEXT = "text"
    const val PLAN_PROPOSED = "plan_proposed"
    const val PLAN_ACCEPTED = "plan_accepted"
    const val PLAN_DECLINED = "plan_declined"
    const val PLAN_AGREED = "plan_agreed"
    const val PLAN_RESCHEDULED = "plan_rescheduled"
    const val PLAN_CHANGED = "plan_changed"
    const val PLAN_CANCELLED = "plan_cancelled"
    const val PLAN_COMPLETED = "plan_completed"
    const val PLAN_VOIDED = "plan_voided"
}

/**
 * The plan a conversation line reports, as the screen holds it.
 *
 * The parts stay nullable: a card that names a moment and an idea says so, and everything it does
 * not know — a place, an idea the catalogue has since lost — has to stay unknown on screen rather
 * than be filled in. `isLatest` is the whole conversation's answer, not the line's own, so an
 * older page can be shown as a promise its pair has already taken back.
 */
data class MessagePlan(
    val activityId: Int?,
    val activityTitle: String?,
    val whenIso: String?,
    // The arrangement this line records, or null for a line the plan entity never wrote. A pair can
    // talk the same idea over more than once, so this — not the activity — is what the tap opens.
    val planId: String?,
    val isLatest: Boolean,
)

data class Message(
    val id: String,
    val matchId: String,
    val senderId: String,
    val body: String,
    val createdAt: String,
    val isRead: Boolean,
    val isOwn: Boolean,
    val kind: String = MessageKinds.TEXT,
    val plan: MessagePlan? = null,
) {
    /** A line the pair's agreement produced, as opposed to a sentence somebody typed. */
    val isPlanEvent: Boolean get() = kind != MessageKinds.TEXT
}

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

/**
 * The states a pair's arrangement moves through, named by the server.
 *
 * The list is the server's own, and the screen reads it rather than re-deriving it: which hour the
 * pair stands on, whose answer is still missing and what may still be called off are decided once by
 * `_status` in `app/services/plan_service.py`, and a client that worked them out again would be a
 * second state machine able to disagree with the first. A status this build does not know is drawn as
 * itself and says it cannot be read — see `presentation/plans/PlanBuckets.kt`.
 */
object PlanStatuses {
    const val PROPOSED = "proposed"
    const val ACCEPTED = "accepted"
    const val PLANNED = "planned"
    const val RESCHEDULED = "rescheduled"
    const val COMPLETED = "completed"
    const val DECLINED = "declined"
    const val CANCELLED = "cancelled"
}

/** What one half has said about an idea the pair is talking over. */
object PlanDecisions {
    const val PENDING = "pending"
    const val JOINED = "joined"
    const val DECLINED = "declined"
}

/**
 * One arrangement of one pair, as both halves of it see it.
 *
 * The shared fields are shared: `note` and `place` are what the pair wrote, so each of them reads the
 * same words. A person's own remark is not here, because it is not a fact about the pair. The two
 * `*Decision` and `*Attended` pairs are one answer seen from either side, and the three flags at the
 * end are the server's answers to the questions the screen would otherwise re-derive: whether the
 * named hour is already behind the pair, whether it is the viewer whose answer is missing, and
 * whether the plan may still be called off.
 */
data class Plan(
    val id: String,
    val title: String,
    val description: String?,
    val note: String?,
    val place: String?,
    val status: String,
    // The hour the pair stands on, and the hour one of them named and the other has not answered.
    // Both stay text: agreeing sends back exactly the instant the person read.
    val startsAt: String?,
    val pendingHour: String?,
    val pendingBy: String?,
    val myDecision: String,
    val iAttended: Boolean,
    val partnerId: String?,
    val partnerName: String?,
    val partnerDecision: String,
    val partnerAttended: Boolean,
    val hourPassed: Boolean,
    val needsMyAnswer: Boolean,
    val canCancel: Boolean,
) {
    /** Whether the hour waiting for an answer is the one the partner named rather than this person's. */
    val partnerNamedTheHour: Boolean
        get() = pendingHour != null && partnerId != null && pendingBy == partnerId
}

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
