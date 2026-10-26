package app.befos.domain.model

data class Interest(
    val slug: String,
    val name: String,
    val category: String,
)

/**
 * One photograph the person owns, under the number the server gave it.
 *
 * The number is what makes the row manageable: removing, leading with and reordering are all writes
 * about a specific photograph, and a bare url cannot name one — two uploads of the same file would
 * be the same string to the server and different rows.
 */
data class ProfilePhoto(val id: String, val url: String)

data class Profile(
    val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    val gender: String,
    val about: String?,
    val datingGoal: String,
    val photos: List<ProfilePhoto>,
    val interests: List<Interest>,
    val lifestyle: Map<String, String>,
    val ageMin: Int,
    val ageMax: Int,
    val genderPreference: List<String>,
    /**
     * The city the deck is filtered to, or null when the person never named one and the deck stays
     * city-unbounded. Only the owner's read carries it — a card of somebody else has no business
     * naming where they search — and the empty text field on the edit screen writes this back to
     * null, which is the answer «снимите фильтр».
     */
    val cityPreference: String? = null,
    val isHidden: Boolean = false,
    /**
     * Whether this account may open the moderation queue. The answer comes from the owner's own
     * profile, and it only decides where to put a door on the screen: the queue routes read the role
     * off the row per request, so an account that draws its way in is stopped by the server.
     */
    val isModerator: Boolean = false,
) {
    /** The row the way every screen reads it: urls, in the order the owner's writes left them. */
    val photoUrls: List<String> get() = photos.map { it.url }

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

/**
 * One worded line of the pair's explanation.
 *
 * [connection] is the engine's own name for how the two answers relate, and it is not decoration: the
 * sentence «Разное отношение: …» read without it is a difference with no kind, and the kind is what
 * tells a person whether they are looking at agreement, at two halves of one thing, or at a
 * conversation. [Connection.UNKNOWN] means the answer never named one — the screen then says nothing
 * about the kind instead of choosing it.
 */
data class Explanation(
    val category: String,
    val label: String,
    val text: String,
    val score: Double,
    val connection: Connection = Connection.UNKNOWN,
)

/**
 * The pair's compatibility document, exactly as the engine wrote it.
 *
 * No number here is the phone's: [overall] is the engine's weighted sum, every [CategoryScore] carries
 * the weight the engine gave it, and the four completeness fields below are the engine's own account of
 * what that sum rests on. [engineVersion] is kept because two versions of the engine can print the same
 * percent from different answers, and a reading that cannot say which one it is cannot be compared with
 * the same pair's reading from last spring.
 *
 * [bandsMeasured] / [bandsTotal] / [measuredWeight] are null when the answer did not say them, which is
 * not the same fact as zero: a document from before stage 125 has no completeness to report, while a
 * document that reports `0 из 7` says the percent stands entirely on the engine's neutral half. The
 * screen has to be able to tell the two apart, and it must not print a bar for a band nobody compared.
 */
data class Compatibility(
    val overall: Int,
    val categories: List<CategoryScore>,
    val strengths: List<Explanation>,
    val differences: List<Explanation>,
    val sharedInterests: List<String>,
    val engineVersion: Int = 1,
    val bandsMeasured: Int? = null,
    val bandsTotal: Int? = null,
    val measuredWeight: Double? = null,
    val starter: String = "",
)

/** One half of the pair, in the pair's own order — the order is identical for both of them. */
data class PairPerson(
    val userId: String,
    val name: String,
)

/**
 * The nearest arrangement the pair has an hour for.
 *
 * [status] is the server's word for which move the plan is on and the screen quotes it rather than
 * re-deriving what `planned` entitles the pair to do; [startsAt] stays the server's text for the same
 * reason every other moment in this file does.
 */
data class PairNextPlan(
    val planId: String,
    val status: String,
    val startsAt: String,
)

/**
 * One reading of a pair, whole: the two people, their number, and what they have agreed.
 *
 * This is the document behind a reading surface, not an editor: everything in it is also reachable from
 * the pair's own screens, and [compatibility] is literally the same document the compatibility page
 * draws, so the digest and the detail cannot disagree about one pair. [plansTotal] and [plan] answer
 * different questions — how many arrangements the pair holds, and which of them has an hour the pair
 * is standing on right now — and neither is derivable from the other.
 */
data class PairProfile(
    val matchId: String,
    val since: String,
    val people: List<PairPerson>,
    val compatibility: Compatibility,
    val plansTotal: Int,
    val plan: PairNextPlan?,
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

/**
 * One person who tapped the account, as the server's like row remembers them.
 *
 * The deck is the only other place this person was ever visible, and it showed them going the
 * other way: until this read existed, a heart that came back never came back as anything.
 * `compatibility` is the percent the tap carried — the number the tapper was shown, read out of
 * the row the tap wrote, not recomputed here; null means the row carries no percent at all, and
 * the row says so rather than borrowing a zero. `likedAt` is the server's instant kept as text,
 * and a row whose text cannot be read as a moment shows no moment.
 */
data class IncomingLike(
    val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    val photoUrl: String?,
    val compatibility: Int?,
    val likedAt: String,
)

/**
 * What the account's own read of its incoming likes answered: the rows it named, and whether
 * it stopped.
 *
 * There is no cursor here, unlike the deck: this page is ordered by when the tap happened, and a
 * tap does not leave the list when it is read — only when the pair forms or the person hides. So
 * the newest fifty are enough to say whether anything older waits behind them, which is exactly
 * what [truncated] claims.
 */
data class LikedMePage(
    val likes: List<IncomingLike>,
    val truncated: Boolean,
)

/**
 * One person the account passed, as the server's own read of those rows names them.
 *
 * A pass used to be readable only as an absence: the deck stopped calling the person, and no other
 * door did either, which made the wrong swipe final without ever saying so. `passedAt` is the
 * server's instant kept as text, and a row whose text cannot be read as a moment shows no moment.
 * There is no percent on this row, because the pass was the answer a card got before any result
 * was worth showing.
 */
data class PassedUser(
    val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    val photoUrl: String?,
    val passedAt: String,
)

/**
 * What the account's own read of its passes answered: the rows it named, and whether it stopped.
 *
 * No cursor, for the same reason the inbox has none — a pass row stays in this list while it is read
 * and leaves only when the account takes it back. So the newest fifty are enough to say whether
 * older answers wait behind them, which is all [truncated] claims.
 */
data class PassedPage(
    val passed: List<PassedUser>,
    val truncated: Boolean,
)

/**
 * One person the account tapped, as the server's own read of those rows names them.
 *
 * The mirror of [IncomingLike]: the same table, the opposite direction. A tap used to leave the
 * account with nothing to read back — the card went out of the deck, the row went into the database,
 * and no door showed either — so reviewing one's own hearts was a matter of memory. `compatibility`
 * is the percent the tap was made carrying, read out of the row rather than recomputed here; null
 * means the row carries no percent, and the row says that instead of borrowing a zero.
 */
data class OutgoingLike(
    val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    val photoUrl: String?,
    val compatibility: Int?,
    val likedAt: String,
)

/**
 * What the account's own read of its taps answered: the rows it named, whether it stopped, and the
 * link that goes past where it stopped.
 *
 * [nextCursor] is the whole difference between a list and a page: stage 116 could say «за ними ждут
 * другие» and leave the reader no way to answer, because the door took no cursor. The key is opaque,
 * built by the server from the last row this page showed, and null exactly when [truncated] is false —
 * a link to a page that does not exist would be a promise the screen then breaks.
 */
data class OutgoingLikesPage(
    val likes: List<OutgoingLike>,
    val truncated: Boolean,
    val nextCursor: String? = null,
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
 * One person the account holds behind a block, as the server lists them.
 *
 * The block was written by this account and only this account's list reads it back, which is the
 * whole reason the screen exists: a tap that dissolved a pair used to be the end of the story, and
 * a person who blocked the wrong card had no way to find out which card it was. `blockedAt` is the
 * server's instant kept as text — the day is what the row shows, and the row shows nothing when the
 * text cannot be read as one.
 */
data class BlockedUser(
    val userId: String,
    val name: String,
    val age: Int,
    val city: String,
    val photoUrl: String?,
    val blockedAt: String,
)

/**
 * One device the account can still open a session on, as the server's own read of its rows named it.
 *
 * Every sign-in, refresh and password change writes one of these, and until this existed the only way
 * to learn that a session you do not recognise is standing was to change the account's word — which
 * ends every session at once, including the one you were reading the answer on. `device` is the text
 * that sign-in sent about itself, null when it said nothing; `current` is the server's answer about
 * which row this very request stood on, so exactly one row carries it and none does when the token
 * predates the claim. Both instants stay the server's text: a row that cannot be read as a moment
 * shows no moment rather than an invented one.
 */
data class DeviceSession(
    val id: String,
    val device: String?,
    val signedInAt: String,
    val expiresAt: String,
    val current: Boolean,
)

/**
 * What the account's own read of its sessions answered: the rows it named, and whether it stopped.
 *
 * [hasMore] is not a door the client can walk through — the route takes no cursor and lists the newest
 * rows only — so a true means the screen is showing fewer devices than the account has signed in on,
 * and the one write that reaches the unnamed rest is the one that ends them all. A section that drew
 * its list without saying this would be reporting a full inventory it never got.
 */
data class SessionsPage(
    val sessions: List<DeviceSession> = emptyList(),
    val hasMore: Boolean = false,
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

/**
 * One plan read by itself: what the pair's record says happened, and the word this person kept for
 * their own eyes.
 *
 * Both arrive in one answer, because the server attaches the journal lines to the plan's own row and
 * the private remark to the reader's member row. Splitting them across two reads would let the page
 * show a chronology the person's own note had not caught up with — and cost the phone a request for
 * every question the plan already answers together.
 */
data class PlanHistory(
    val lines: List<Message>,
    // This person's own remark about their own plan. The other half never sees this field, and the
    // pair's journal never carries it, which is why the page can call it private and mean it.
    val myNote: String?,
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
    // Null means «untouched», the same split `about` lives by. The client cannot send a JSON null
    // (the serializer drops explicit nulls), so the empty string is the only erase it owns — and
    // the server reads it as «снимите фильтр».
    val cityPreference: String? = null,
    val isHidden: Boolean? = null,
)

/**
 * The account a complaint names, as the queue draws it.
 *
 * `age` is null rather than zero for an erased account: the birth date an erasure writes belongs to
 * nobody, and a card that printed «0» for it would put a number on the screen that a person never
 * was. The two flags say what the queue has to say about a row it cannot open as a profile — hidden
 * from the deck, or gone from it altogether.
 */
data class ReportedAccount(
    val userId: String,
    val name: String?,
    val age: Int?,
    val city: String?,
    val isDeleted: Boolean,
    val isHidden: Boolean,
    val isModerator: Boolean,
)

/** The account that filed the complaint. The queue names it to the moderator and to nobody else. */
data class Reporter(val userId: String, val name: String?)

data class ReportCard(
    val id: String,
    val reason: String,
    val details: String?,
    val status: String,
    val createdAt: String,
    val reported: ReportedAccount,
    val reporter: Reporter,
)

/**
 * One page of the queue, oldest complaint first.
 *
 * `nextCursor` is the id of the last row this page answered with, and `hasMore` says whether a row
 * stands behind it. A screen that read `hasMore` off the page being shorter than the limit would
 * stop looking for complaints in the middle of the queue whenever the last page happened to land
 * exactly on the bound.
 */
data class ReportsPage(
    val reports: List<ReportCard>,
    val nextCursor: String?,
    val hasMore: Boolean,
)

data class ReportReviewRow(
    val id: String,
    val moderatorId: String,
    val moderatorName: String?,
    val fromStatus: String,
    val toStatus: String,
    val comment: String?,
    val decidedAt: String,
)

/**
 * One complaint with the whole history of how it was decided, and the statuses it may still be moved
 * to. The choices come from the server's own transition table rather than from a list the client
 * keeps, so a screen cannot offer a tap the write route was always going to refuse.
 */
data class ReportDetail(
    val card: ReportCard,
    val updatedAt: String,
    val reviews: List<ReportReviewRow>,
    val allowedNextStatuses: List<String>,
)

/** The status the row holds now, as the write route answered it after its own commit. */
data class ReviewOutcome(val id: String, val status: String, val updatedAt: String)

/**
 * How many rows of one kind the account's own file carries.
 *
 * The number comes from the document the server wrote, not from a count the client keeps: the file
 * and the screen have to be able to say the same thing about the same life, and the file is the one
 * that can be checked after the account is gone.
 */
data class ExportSection(val name: String, val rows: Int)

/**
 * One account's own rows, handed over as a file the person can keep.
 *
 * The app can erase all of them in one tap — «Аккаунт удалится сразу. Восстановить его не получится»
 * on the settings screen says so — and a door that closes a life with nothing taken out of it is a
 * door worth standing in front of twice. So the bytes arrive here unchanged from the server: this
 * class adds the two things a person needs to decide what to do with them, where the rows stand and
 * whether any section was cut.
 *
 * [truncated] is the honest half. A section the server capped is named, and the file is not allowed
 * to be presented as complete while it holds a part of a list.
 */
class AccountExport(
    val bytes: ByteArray,
    val fileName: String,
    val generatedAt: String,
    val sections: List<ExportSection>,
    val truncated: List<String>,
) {
    val sizeBytes: Int get() = bytes.size

    /** Rows the file carries across every section — the number the screen prints next to the name. */
    val totalRows: Int get() = sections.sumOf { it.rows }

    /**
     * Whether the file holds nothing anybody did — only the rows that name the account and the device
     * it is read from.
     *
     * A fresh account is a real state and is drawn as one: the file still comes back, because an empty
     * document is the answer «здесь пока только то, что вы ввели сами», and not a failure. The sections
     * left out of the question are the ones an account cannot hold empty — the questionnaire row the
     * onboarding writes, the session row this very request stands on — so a person who signed up an
     * hour ago is not told their file is full.
     */
    val isFreshAccount: Boolean
        get() = sections.filter { it.name in ACTIVITY_SECTIONS }.all { it.rows == 0 }

    companion object {
        /** The counts that say a life happened here, as the document names them. */
        private val ACTIVITY_SECTIONS = setOf(
            "photos",
            "questionnaire_answers",
            "taps_given",
            "taps_received",
            "taps_passed",
            "deck",
            "pairs",
            "chats",
            "plans",
            "blocks",
            "complaints",
        )
    }
}
