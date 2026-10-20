package app.befos.data.remote

import app.befos.core.network.ApiConfig
import app.befos.core.network.ApiResult
import app.befos.core.network.apiCall
import app.befos.core.network.apiCallUnit
import app.befos.data.model.AnswersRequest
import app.befos.data.model.AuthResponseDto
import app.befos.data.model.BlockedUsersDto
import app.befos.data.model.ChangePasswordRequest
import app.befos.data.model.CompatibilityDto
import app.befos.data.model.UniverseDto
import app.befos.data.model.DiscoveryPageDto
import app.befos.data.model.InterestListDto
import app.befos.data.model.LikedMeDto
import app.befos.data.model.LikeResponseDto
import app.befos.data.model.LoginRequest
import app.befos.data.model.MatchDetailDto
import app.befos.data.model.MatchListDto
import app.befos.data.model.MeetingTimeRequest
import app.befos.data.model.MessageDto
import app.befos.data.model.MessagePageDto
import app.befos.data.model.MessageRequest
import app.befos.data.model.OnboardingRequest
import app.befos.data.model.PassResponseDto
import app.befos.data.model.PassedUsersDto
import app.befos.data.model.PhotoOrderRequest
import app.befos.data.model.PlanDetailDto
import app.befos.data.model.PlanEditRequest
import app.befos.data.model.PlanListDto
import app.befos.data.model.ProfileDto
import app.befos.data.model.ProfileUpdateRequest
import app.befos.data.model.ProgressDto
import app.befos.data.model.PublicProfileDto
import app.befos.data.model.RecommendationListDto
import app.befos.data.model.RefreshRequest
import app.befos.data.model.RegisterRequest
import app.befos.data.model.ReportRequest
import app.befos.data.model.ReportDetailDto
import app.befos.data.model.ReportsPageDto
import app.befos.data.model.ReviewRequest
import app.befos.data.model.ReviewResultDto
import app.befos.data.model.SessionsDto
import app.befos.data.model.TestListDto
import app.befos.data.model.TestProfileDto
import app.befos.data.model.TestResultDto
import app.befos.data.model.TokenPairDto
import app.befos.data.model.VisibilityRequest
import io.ktor.client.HttpClient
import io.ktor.client.plugins.timeout
import io.ktor.client.request.forms.MultiPartFormDataContent
import io.ktor.client.request.forms.formData
import io.ktor.client.request.parameter
import io.ktor.client.request.setBody
import io.ktor.client.request.url
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpMethod
import java.io.InputStream

/**
 * Thin typed wrapper over every backend REST endpoint. Each call returns an
 * [ApiResult] so callers never deal with raw HTTP exceptions.
 */
class ApiService(private val client: HttpClient) {

    private fun endpoint(path: String): String = ApiConfig.api(path)

    // ---------- Auth ----------
    suspend fun register(email: String, password: String): ApiResult<AuthResponseDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("auth/register"))
            setBody(RegisterRequest(email, password, password))
        }

    suspend fun login(email: String, password: String): ApiResult<AuthResponseDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("auth/login"))
            setBody(LoginRequest(email, password))
        }

    suspend fun refresh(refreshToken: String): ApiResult<TokenPairDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("auth/refresh"))
            setBody(RefreshRequest(refreshToken))
        }

    suspend fun logout(refreshToken: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("auth/logout"))
            setBody(RefreshRequest(refreshToken))
        }

    /**
     * Replace the account's own word with one the caller says twice.
     *
     * The answer carries no token pair on purpose: the server revokes the session this call was made
     * from together with every other one the account holds, so a fresh pair would be a promise the
     * backend has just broken. The body names no account — the bearer token already said whose.
     */
    suspend fun changePassword(
        oldPassword: String,
        newPassword: String,
        passwordConfirm: String,
    ): ApiResult<Unit> = client.apiCallUnit {
        method = HttpMethod.Post
        url(endpoint("auth/change-password"))
        setBody(ChangePasswordRequest(oldPassword, newPassword, passwordConfirm))
    }

    // ---------- Sessions ----------
    /**
     * The devices this account can still open a token pair on, newest first.
     *
     * The request names no account: the bearer token already said whose, and a list built from anything
     * the client could pass would be a door to somebody else's sessions. One row can answer `current:
     * true` — the row this very request stands on — because the access token carries that row's id, and
     * none does when the token was minted before the claim existed.
     */
    suspend fun sessions(): ApiResult<SessionsDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("auth/sessions"))
        }

    /**
     * End one of the account's own sessions by the id the list gave it.
     *
     * A 204 here says the row was cut, not that a token already signed died with it: the product revokes
     * sessions, and an access token handed out earlier stays readable until it expires on its own. An id
     * that is foreign, already ended, or past its expiry answers the same refusal as an id that was
     * never written, so this is not a place to find out which sessions existed.
     */
    suspend fun revokeSession(sessionId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("auth/sessions/$sessionId/revoke"))
        }

    /**
     * End every session the account holds, this device's row among them.
     *
     * The answer carries no token pair for the same reason `changePassword`'s does: the row this request
     * stands on is among the rows it ends, so a fresh pair would be the server un-revoking its own
     * write. The caller is signed out at its next refresh, like every other device.
     */
    suspend fun revokeAllSessions(): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("auth/sessions/revoke-all"))
        }

    // ---------- Users / Profile ----------
    suspend fun getMe(): ApiResult<ProfileDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("users/me"))
        }

    suspend fun completeOnboarding(request: OnboardingRequest): ApiResult<ProfileDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("users/me/onboarding"))
            setBody(request)
        }

    suspend fun updateProfile(request: ProfileUpdateRequest): ApiResult<ProfileDto> =
        client.apiCall {
            method = HttpMethod.Patch
            url(endpoint("users/me"))
            setBody(request)
        }

    suspend fun getInterests(): ApiResult<InterestListDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("users/interests"))
        }

    suspend fun getPublicProfile(userId: String): ApiResult<PublicProfileDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("users/$userId"))
        }

    suspend fun uploadPhoto(input: InputStream, contentType: String): ApiResult<ProfileDto> {
        val bytes = input.use { it.readBytes() }
        val multipart = MultiPartFormDataContent(
            formData {
                append(
                    "file",
                    bytes,
                    Headers.build {
                        append(HttpHeaders.ContentType, contentType)
                        append(HttpHeaders.ContentDisposition, "filename=\"photo.jpg\"")
                    },
                )
            },
        )
        return client.apiCall {
            method = HttpMethod.Post
            url(endpoint("users/me/photo"))
            setBody(multipart)
            // The client's own bounds are sized for a JSON answer, and this call is sized by the
            // uplink: measured on a link that drained 2.4 MB in 37 s, the inherited ten-second
            // write default ended the upload while bytes were still moving, and the declared
            // whole-call ceiling would have ended it at 35 s. A stalled upload still ends — the
            // sixty seconds here is silence, not progress — but a slow one gets through.
            timeout {
                socketTimeoutMillis = 60_000
                requestTimeoutMillis = 600_000
            }
        }
    }

    suspend fun deletePhoto(photoId: String): ApiResult<ProfileDto> =
        client.apiCall {
            method = HttpMethod.Delete
            url(endpoint("users/me/photo/$photoId"))
        }

    suspend fun makePhotoPrimary(photoId: String): ApiResult<ProfileDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("users/me/photo/$photoId/primary"))
        }

    suspend fun reorderPhotos(photoIds: List<String>): ApiResult<ProfileDto> =
        client.apiCall {
            method = HttpMethod.Patch
            url(endpoint("users/me/photo/order"))
            setBody(PhotoOrderRequest(photoIds))
        }

    // ---------- Tests ----------
    suspend fun getTests(): ApiResult<TestListDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("tests"))
        }

    suspend fun getProgress(): ApiResult<ProgressDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("tests/progress"))
        }

    suspend fun submitAnswers(request: AnswersRequest): ApiResult<ProgressDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("tests/answers"))
            setBody(request)
        }

    suspend fun completeTest(): ApiResult<TestResultDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("tests/complete"))
        }

    /**
     * The person's own profile, read back. Not a second way to finish the test: `completeTest`
     * writes — it rescores the answers, re-ranks the deck and refreshes the pair percents — and
     * refuses a questionnaire it still counts short, so it cannot be what a screen asks when it
     * only wants to show what is already stored. This call answers with the same two lists and the
     * moment the engine last rebuilt them, and it carries no user identifier: the token says whose
     * profile it is.
     */
    suspend fun getProfile(): ApiResult<TestProfileDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("tests/profile"))
        }

    // ---------- Discovery ----------
    suspend fun discover(limit: Int = 20, cursor: String? = null): ApiResult<DiscoveryPageDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("discover"))
            parameter("limit", limit)
            if (cursor != null) parameter("cursor", cursor)
        }

    /**
     * Who tapped this account, newest first, at most fifty of them. The deck never showed the
     * tap: a card leaves it once the account answers, so a heart that came back had no place to
     * be read. No identifier travels with this call — the token says whose inbox it is — and the
     * percent each row carries is the one the tap was made carrying, not a fresh score.
     */
    suspend fun likedMe(): ApiResult<LikedMeDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("discover/liked-me"))
        }

    suspend fun like(userId: String): ApiResult<LikeResponseDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("users/$userId/like"))
        }

    suspend fun pass(userId: String): ApiResult<PassResponseDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("users/$userId/pass"))
        }

    /**
     * Whom the account passed, newest answer first, at most fifty of them.
     *
     * The deck answers this by silence — a person it has an answer for simply never comes back — so
     * the only way to learn the list until now was to notice who was missing. No identifier travels
     * with this call either: the token says whose passes these are.
     */
    suspend fun passedUsers(): ApiResult<PassedUsersDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("discover/passed"))
        }

    /**
     * Takes one pass back. The answer is the list that stands after the write, the way the unblock
     * answers: the screen paints the rows the server holds rather than the row the tap named.
     */
    suspend fun unpass(userId: String): ApiResult<PassedUsersDto> =
        client.apiCall {
            method = HttpMethod.Delete
            url(endpoint("users/$userId/pass"))
        }

    // ---------- Matches ----------
    suspend fun getMatches(): ApiResult<MatchListDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("matches"))
        }

    suspend fun getMatch(matchId: String): ApiResult<MatchDetailDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("matches/$matchId"))
        }

    suspend fun getCompatibility(matchId: String): ApiResult<CompatibilityDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("matches/$matchId/compatibility"))
        }

    /** The same pair scored by the same engine, but answered node by node instead of one bar. */
    suspend fun getUniverse(matchId: String): ApiResult<UniverseDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("matches/$matchId/universe"))
        }

    suspend fun getRecommendations(matchId: String, force: Boolean = false): ApiResult<RecommendationListDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("matches/$matchId/recommendations"))
            parameter("force", force)
        }

    suspend fun selectRecommendation(matchId: String, activityId: Int): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("matches/$matchId/recommendations/$activityId/select"))
        }

    suspend fun declineRecommendation(matchId: String, activityId: Int): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("matches/$matchId/recommendations/$activityId/decline"))
        }

    suspend fun restoreRecommendation(matchId: String, activityId: Int): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Delete
            url(endpoint("matches/$matchId/recommendations/$activityId/decline"))
        }

    /**
     * A PUT rather than a POST: the pair holds one row per person per card, so naming a second
     * hour replaces this person's offer instead of leaving the partner two moments to choose
     * between.
     */
    suspend fun proposeMeetingTime(matchId: String, activityId: Int, whenIso: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Put
            url(endpoint("matches/$matchId/recommendations/$activityId/time"))
            setBody(MeetingTimeRequest(whenIso))
        }

    /** The instant travels back as it was read, so an offer that moved in between is refused. */
    suspend fun acceptMeetingTime(matchId: String, activityId: Int, whenIso: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("matches/$matchId/recommendations/$activityId/time/accept"))
            setBody(MeetingTimeRequest(whenIso))
        }

    /** Ends the pair without blocking the person: the row and everything hanging under it go. */
    suspend fun dissolveMatch(matchId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Delete
            url(endpoint("matches/$matchId"))
        }

    // ---------- Chat ----------
    suspend fun getMessages(matchId: String, limit: Int = 50, beforeId: String? = null): ApiResult<MessagePageDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("matches/$matchId/messages"))
            parameter("limit", limit)
            if (beforeId != null) parameter("before_id", beforeId)
        }

    suspend fun sendMessage(
        matchId: String,
        body: String,
        clientMsgId: String? = null,
    ): ApiResult<MessageDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("matches/$matchId/messages"))
            setBody(MessageRequest(body, clientMsgId))
        }

    /**
     * Take back a line the person typed. The answer is empty on purpose: the words are gone, so
     * there is nothing left to hand back, and a line that is not the caller's own — a partner's, a
     * page of the pair's plan, one already taken back — is refused by the same route and says no
     * more about itself than an id that never was a line.
     */
    suspend fun recallMessage(matchId: String, messageId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Delete
            url(endpoint("matches/$matchId/messages/$messageId"))
        }

    suspend fun markRead(matchId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("matches/$matchId/read"))
        }

    // ---------- Shared plans ----------
    /**
     * One pair's arrangements, as the pair's screen reads them.
     *
     * The list is asked for by the pair, not by the person: the screen a pair opens is about the two
     * of them, and the session already says whose eyes it is drawn for. No id of a person or of a plan
     * is sent anywhere as a claim about rights — the routes resolve the owner themselves.
     */
    suspend fun getMatchPlans(matchId: String): ApiResult<PlanListDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("matches/$matchId/plans"))
        }

    /**
     * One plan by itself, for the device that holds an alarm about it and no pair page in front of it.
     *
     * The reminder was armed by a page the person has probably left, and the pair's hour can move
     * behind that page; this read is what the waking device has to compare its own sentence against.
     * Only the plan is asked for, never a person id, so the session still decides whose plan this is.
     */
    suspend fun getPlan(planId: String): ApiResult<PlanDetailDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("plans/$planId"))
        }

    /** Stand behind the idea the plan is about — the same act as tapping «выбрать» on the card. */
    suspend fun acceptPlan(planId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("plans/$planId/accept"))
        }

    suspend fun declinePlan(planId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("plans/$planId/decline"))
        }

    suspend fun restorePlanDecline(planId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Delete
            url(endpoint("plans/$planId/decline"))
        }

    /** Name — or move — the hour this person would meet at. The hour stays a projection of the pair's rows. */
    suspend fun offerPlanHour(planId: String, whenIso: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("plans/$planId/hour"))
            setBody(MeetingTimeRequest(whenIso))
        }

    /** The instant travels back as it was read, so an offer that moved in between is refused, not agreed to. */
    suspend fun confirmPlanHour(planId: String, whenIso: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("plans/$planId/hour/confirm"))
            setBody(MeetingTimeRequest(whenIso))
        }

    suspend fun cancelPlan(planId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("plans/$planId/cancel"))
        }

    /** Take a cancellation back — by the half that called it off, and by nobody else. */
    suspend fun restorePlan(planId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Delete
            url(endpoint("plans/$planId/cancel"))
        }

    /**
     * This person's own word that the meeting happened. One tap answers 204 and can still leave the
     * plan planned: «состоялось» is the pair's, not one half's, and the clock never says it.
     */
    suspend fun markPlanAttended(planId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("plans/$planId/complete"))
        }

    suspend fun undoPlanAttended(planId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Delete
            url(endpoint("plans/$planId/complete"))
        }

    /**
     * Write the pair's place and their note about it, or take one of them back.
     *
     * Only these two words, and only through these two flags: the hour belongs to both halves and
     * moves through the hour routes, while a place that was written and then erased has to be said as
     * an erasure — an omitted field means «не трогать», not «пусто». The answer carries the plan as it
     * now stands and is dropped here on purpose: the page that sent the tap reads its whole list back,
     * so no card can be repainted from one response and disagree with the section it sits in.
     */
    suspend fun editPlanWords(
        planId: String,
        place: String?,
        note: String?,
        clearPlace: Boolean,
        clearNote: Boolean,
    ): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Patch
            url(endpoint("plans/$planId"))
            setBody(PlanEditRequest(place, note, clearPlace, clearNote))
        }

    // ---------- Safety ----------
    suspend fun block(userId: String): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("users/$userId/block"))
        }

    /**
     * Takes one block back. The answer is the list that survives the write, not a bare ok: the
     * screen paints the rows the server holds rather than the row it hoped to delete.
     */
    suspend fun unblock(userId: String): ApiResult<BlockedUsersDto> =
        client.apiCall {
            method = HttpMethod.Delete
            url(endpoint("users/$userId/block"))
        }

    suspend fun blockedUsers(): ApiResult<BlockedUsersDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("users/me/blocks"))
        }

    suspend fun report(userId: String, reason: String, details: String?): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("users/$userId/report"))
            setBody(ReportRequest(reason, details))
        }

    suspend fun setVisibility(hidden: Boolean): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Post
            url(endpoint("users/me/visibility"))
            setBody(VisibilityRequest(hidden))
        }

    suspend fun deleteAccount(): ApiResult<Unit> =
        client.apiCallUnit {
            method = HttpMethod.Delete
            url(endpoint("users/me"))
        }

    // ---------- Moderation ----------
    /**
     * One page of the complaint queue, oldest first, narrowed to one status when one is named.
     *
     * `afterId` is the id of the last row the previous page answered with rather than an offset: the
     * queue is written while it is being read, and a page numbered by position would show the same
     * complaint twice as soon as somebody ahead of it arrived. A null filter is dropped instead of
     * sent, because an empty status is a status nobody declares.
     */
    suspend fun reports(status: String?, afterId: String?, limit: Int): ApiResult<ReportsPageDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("reports"))
            parameter("limit", limit)
            if (status != null) parameter("status", status)
            if (afterId != null) parameter("after_id", afterId)
        }

    suspend fun reportDetail(reportId: String): ApiResult<ReportDetailDto> =
        client.apiCall {
            method = HttpMethod.Get
            url(endpoint("reports/$reportId"))
        }

    /**
     * Moves one complaint to one status and records the note that says why.
     *
     * The moderator is not in the body: the row that writes history takes the hand from the session
     * that signed in, so a client cannot put another name on the line than its own.
     */
    suspend fun reviewReport(
        reportId: String,
        status: String,
        comment: String?,
    ): ApiResult<ReviewResultDto> =
        client.apiCall {
            method = HttpMethod.Post
            url(endpoint("reports/$reportId/review"))
            setBody(ReviewRequest(status, comment))
        }
}
