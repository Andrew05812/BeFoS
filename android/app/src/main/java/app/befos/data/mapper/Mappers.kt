package app.befos.data.mapper

import app.befos.core.network.ApiConfig
import app.befos.data.model.CategoryProgressDto
import app.befos.data.model.CategoryScoreDto
import app.befos.data.model.CompatibilityDto
import app.befos.data.model.DiscoveryCardDto
import app.befos.data.model.ExplanationItemDto
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
import app.befos.data.model.TestListDto
import app.befos.data.model.TestProfileDto
import app.befos.data.model.TestResultDto
import app.befos.data.model.TraitAxisDto
import app.befos.data.model.UniverseDto
import app.befos.data.model.UniverseLayerDto
import app.befos.data.model.UniverseNodeDto
import app.befos.domain.model.CategoryProgress
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Compatibility
import app.befos.domain.model.Connection
import app.befos.domain.model.DiscoveryCard
import app.befos.domain.model.Explanation
import app.befos.domain.model.Interest
import app.befos.domain.model.MatchSummary
import app.befos.domain.model.Message
import app.befos.domain.model.MessagePlan
import app.befos.domain.model.OnboardingData
import app.befos.domain.model.Option
import app.befos.domain.model.Profile
import app.befos.domain.model.ProfileUpdateData
import app.befos.domain.model.PublicProfile
import app.befos.domain.model.Question
import app.befos.domain.model.Plan
import app.befos.domain.model.Recommendation
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
    photoUrls = photos.mapNotNull { ApiConfig.absolute(it.url) },
    interests = interests.map { it.toDomain() },
    lifestyle = lifestyle,
    ageMin = ageMin,
    ageMax = ageMax,
    genderPreference = genderPreference,
    isHidden = isHidden,
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
    isHidden = isHidden,
)
