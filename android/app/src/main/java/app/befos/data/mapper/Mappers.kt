package app.befos.data.mapper

import app.befos.core.network.ApiConfig
import app.befos.data.model.BlockedUserDto
import app.befos.data.model.CategoryProgressDto
import app.befos.data.model.CategoryScoreDto
import app.befos.data.model.CompatibilityDto
import app.befos.data.model.DiscoveryCardDto
import app.befos.data.model.ExplanationItemDto
import app.befos.data.model.IncomingLikeDto
import app.befos.data.model.InterestDto
import app.befos.data.model.MatchSummaryDto
import app.befos.data.model.MessageDto
import app.befos.data.model.OnboardingRequest
import app.befos.data.model.OptionDto
import app.befos.data.model.PlanDto
import app.befos.data.model.ProfileDto
import app.befos.data.model.ProfileUpdateRequest
import app.befos.data.model.ProgressDto
import app.befos.data.model.PublicProfileDto
import app.befos.data.model.QuestionDto
import app.befos.data.model.RecommendationDto
import app.befos.data.model.ReportCardDto
import app.befos.data.model.ReportDetailDto
import app.befos.data.model.ReportReviewRowDto
import app.befos.data.model.ReportedAccountDto
import app.befos.data.model.ReporterDto
import app.befos.data.model.ReportsPageDto
import app.befos.data.model.ReviewResultDto
import app.befos.data.model.SessionDto
import app.befos.data.model.SessionsDto
import app.befos.data.model.TestListDto
import app.befos.data.model.TestProfileDto
import app.befos.data.model.TestResultDto
import app.befos.data.model.TraitAxisDto
import app.befos.data.model.UniverseDto
import app.befos.data.model.UniverseLayerDto
import app.befos.data.model.UniverseNodeDto
import app.befos.domain.model.BlockedUser
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Compatibility
import app.befos.domain.model.Connection
import app.befos.domain.model.DeviceSession
import app.befos.domain.model.DiscoveryCard
import app.befos.domain.model.Explanation
import app.befos.domain.model.IncomingLike
import app.befos.domain.model.Interest
import app.befos.domain.model.MatchSummary
import app.befos.domain.model.Message
import app.befos.domain.model.MessagePlan
import app.befos.domain.model.OnboardingData
import app.befos.domain.model.Option
import app.befos.domain.model.Profile
import app.befos.domain.model.ProfilePhoto
import app.befos.domain.model.ProfileUpdateData
import app.befos.domain.model.PublicProfile
import app.befos.domain.model.Question
import app.befos.domain.model.Plan
import app.befos.domain.model.Recommendation
import app.befos.domain.model.ReportCard
import app.befos.domain.model.ReportDetail
import app.befos.domain.model.ReportReviewRow
import app.befos.domain.model.ReportedAccount
import app.befos.domain.model.Reporter
import app.befos.domain.model.ReportsPage
import app.befos.domain.model.ReviewOutcome
import app.befos.domain.model.SessionsPage
import app.befos.domain.model.Activity
import app.befos.domain.model.TestProfile
import app.befos.domain.model.TestProgress
import app.befos.domain.model.TraitAxis
import app.befos.domain.model.Universe
import app.befos.domain.model.UniverseLayer
import app.befos.domain.model.UniverseNode

fun InterestDto.toDomain() = Interest(slug, name, category)

fun ProfileDto.toDomain() = Profile(
    userId = userId,
    name = name,
    age = age,
    city = city,
    gender = gender,
    about = about,
    datingGoal = datingGoal,
    photos = photos.mapNotNull { photo ->
        // A url this build cannot resolve is dropped rather than sent on as a broken tile; its
        // number goes with it, so the row the screen manages is the row it can actually paint.
        ApiConfig.absolute(photo.url)?.let { ProfilePhoto(id = photo.id, url = it) }
    },
    interests = interests.map { it.toDomain() },
    lifestyle = lifestyle,
    ageMin = ageMin,
    ageMax = ageMax,
    genderPreference = genderPreference,
    cityPreference = cityPreference,
    isHidden = isHidden,
    isModerator = isModerator,
)

fun OptionDto.toDomain() = Option(id, text)

fun QuestionDto.toDomain() = Question(
    id = id,
    category = category,
    trait = trait,
    text = text,
    options = options.map { it.toDomain() },
    selectedOptionId = selectedOptionId,
    kind = kind,
)

fun CategoryProgressDto.toDomain() = CategoryProgress(key, label, total, answered)

fun ProgressDto.toDomain() = TestProgress(
    answered = answered,
    total = total,
    percent = percent,
    remaining = remaining,
    completed = completed,
    categories = categories.map { it.toDomain() },
)

fun CategoryScoreDto.toDomain() = CategoryScore(category, label, score, weight, hasData)

fun TraitAxisDto.toDomain() = TraitAxis(category, trait, label, value, side)

fun TestResultDto.toDomain() = TestProfile(
    categories = categories.map { it.toDomain() },
    axes = axes.map { it.toDomain() },
)

fun TestProfileDto.toDomain() = TestProfile(
    categories = categories.map { it.toDomain() },
    axes = axes.map { it.toDomain() },
    updatedAt = updatedAt,
)

fun ExplanationItemDto.toDomain() = Explanation(category, label, text, score)

fun CompatibilityDto.toDomain() = Compatibility(
    overall = overall,
    categories = categories.map { it.toDomain() },
    strengths = strengths.map { it.toDomain() },
    differences = differences.map { it.toDomain() },
    sharedInterests = sharedInterests,
)

fun UniverseNodeDto.toDomain() = UniverseNode(
    key = key,
    label = label,
    aValue = aValue,
    bValue = bValue,
    hasData = hasData,
    connection = Connection.fromJson(connection),
    evidence = evidence,
    confidence = confidence,
    suggestion = suggestion,
    questions = questions,
)

fun UniverseLayerDto.toDomain() = UniverseLayer(
    category = category,
    label = label,
    score = score,
    weight = weight,
    hasData = hasData,
    coverage = coverage,
    confidence = confidence,
    nodes = nodes.map { it.toDomain() },
)

fun UniverseDto.toDomain() = Universe(
    overall = overall,
    engineVersion = engineVersion,
    aUserId = aUserId,
    bUserId = bUserId,
    layers = layers.map { it.toDomain() },
    story = story,
)

fun DiscoveryCardDto.toDomain() = DiscoveryCard(
    userId = userId,
    name = name,
    age = age,
    city = city,
    about = about,
    datingGoal = datingGoal,
    photoUrl = ApiConfig.absolute(photoUrl),
    interests = interests,
    compatibility = compatibility,
    sharedInterestsCount = sharedInterestsCount,
    highlight = highlight,
)

fun IncomingLikeDto.toDomain() = IncomingLike(
    userId = userId,
    name = name,
    age = age,
    city = city,
    photoUrl = ApiConfig.absolute(photoUrl),
    compatibility = compatibility,
    likedAt = likedAt,
)

fun PublicProfileDto.toDomain() = PublicProfile(
    userId = userId,
    name = name,
    age = age,
    city = city,
    about = about,
    datingGoal = datingGoal,
    gender = gender,
    interests = interests,
    photoUrls = photos.mapNotNull { ApiConfig.absolute(it) },
    compatibility = compatibility,
    categories = categories.map { it.toDomain() },
    sharedInterests = sharedInterests,
)

fun MatchSummaryDto.toDomain() = MatchSummary(
    matchId = matchId,
    userId = userId,
    name = name,
    age = age,
    city = city,
    photoUrl = ApiConfig.absolute(photoUrl),
    compatibility = compatibility,
    lastMessage = lastMessage,
    lastMessageAt = lastMessageAt,
    unread = unread,
)

fun BlockedUserDto.toDomain() = BlockedUser(
    userId = userId,
    name = name,
    age = age,
    city = city,
    photoUrl = ApiConfig.absolute(photoUrl),
    blockedAt = blockedAt,
)

/** Nothing here is made up: the row's own text is what the person has to recognise their device in. */
fun SessionDto.toDomain() = DeviceSession(
    id = id,
    device = device?.trim()?.ifEmpty { null },
    signedInAt = signedInAt,
    expiresAt = expiresAt,
    current = current,
)

fun SessionsDto.toDomain() = SessionsPage(
    sessions = sessions.map { it.toDomain() },
    hasMore = hasMore,
)

fun MessageDto.toDomain() = Message(
    id = id,
    matchId = matchId,
    senderId = senderId,
    body = body,
    createdAt = createdAt,
    isRead = isRead,
    isOwn = isOwn,
    kind = kind,
    plan = plan?.let {
        MessagePlan(
            activityId = it.activityId,
            activityTitle = it.activityTitle,
            whenIso = it.whenIso,
            planId = it.planId,
            isLatest = it.isLatest,
        )
    },
)

fun RecommendationDto.toDomain() = Recommendation(
    activity = Activity(
        id = activity.id,
        slug = activity.slug,
        title = activity.title,
        description = activity.description,
        category = activity.category,
    ),
    score = score,
    position = position,
    reasons = reasons,
    selected = selected,
    partnerSelected = partnerSelected,
    declined = declined,
    myMeetingTime = myMeetingTime,
    partnerMeetingTime = partnerMeetingTime,
    iAcceptedTime = iAcceptedTime,
    agreedTime = agreedTime,
)

/**
 * The plan as the pair's screen holds it. The hours stay text rather than becoming instants: the
 * screen prints them on this person's calendar and sends back exactly what it showed, and a value
 * parsed and re-printed on the way could name a moment nobody offered.
 */
fun PlanDto.toDomain() = Plan(
    id = id,
    title = title,
    description = description,
    note = note,
    place = place,
    status = status,
    startsAt = startsAt,
    pendingHour = pendingHour,
    pendingBy = pendingBy,
    myDecision = myDecision,
    iAttended = iAttended,
    partnerId = partnerId,
    partnerName = partnerName,
    partnerDecision = partnerDecision,
    partnerAttended = partnerAttended,
    hourPassed = hourPassed,
    needsMyAnswer = needsMyAnswer,
    canCancel = canCancel,
)

fun OnboardingData.toRequest() = OnboardingRequest(
    name = name,
    birthDate = birthDate,
    city = city,
    gender = gender,
    about = about,
    datingGoal = datingGoal,
    interests = interests,
    lifestyle = lifestyle,
    ageMin = ageMin,
    ageMax = ageMax,
    genderPreference = genderPreference,
)

fun ProfileUpdateData.toRequest() = ProfileUpdateRequest(
    name = name,
    city = city,
    about = about,
    datingGoal = datingGoal,
    gender = gender,
    birthDate = birthDate,
    interests = interests,
    lifestyle = lifestyle,
    ageMin = ageMin,
    ageMax = ageMax,
    genderPreference = genderPreference,
    cityPreference = cityPreference,
    isHidden = isHidden,
)

fun ReportedAccountDto.toDomain() = ReportedAccount(
    userId = userId,
    name = name,
    age = age,
    city = city,
    isDeleted = isDeleted,
    isHidden = isHidden,
    isModerator = isModerator,
)

fun ReporterDto.toDomain() = Reporter(userId = userId, name = name)

fun ReportCardDto.toDomain() = ReportCard(
    id = id,
    reason = reason,
    details = details,
    status = status,
    createdAt = createdAt,
    reported = reported.toDomain(),
    reporter = reporter.toDomain(),
)

fun ReportsPageDto.toDomain() = ReportsPage(
    reports = reports.map { it.toDomain() },
    nextCursor = nextCursor,
    hasMore = hasMore,
)

fun ReportReviewRowDto.toDomain() = ReportReviewRow(
    id = id,
    moderatorId = moderatorId,
    moderatorName = moderatorName,
    fromStatus = fromStatus,
    toStatus = toStatus,
    comment = comment,
    decidedAt = decidedAt,
)

/**
 * The flat detail answer folded back into the card the queue already draws.
 *
 * The route answers one object rather than a card inside a detail, so the row a moderator opens and
 * the row the list still shows are the same fields read the same way — and the screen that repaints
 * after a decision has one place to take the card from.
 */
fun ReportDetailDto.toDomain() = ReportDetail(
    card = ReportCard(
        id = id,
        reason = reason,
        details = details,
        status = status,
        createdAt = createdAt,
        reported = reported.toDomain(),
        reporter = reporter.toDomain(),
    ),
    updatedAt = updatedAt,
    reviews = reviews.map { it.toDomain() },
    allowedNextStatuses = allowedNextStatuses,
)

fun ReviewResultDto.toDomain() = ReviewOutcome(id = id, status = status, updatedAt = updatedAt)
