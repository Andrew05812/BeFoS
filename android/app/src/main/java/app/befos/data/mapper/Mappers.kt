package app.befos.data.mapper

import app.befos.core.network.ApiConfig
import app.befos.data.model.CategoryScoreDto
import app.befos.data.model.CompatibilityDto
import app.befos.data.model.DiscoveryCardDto
import app.befos.data.model.ExplanationItemDto
import app.befos.data.model.InterestDto
import app.befos.data.model.MatchSummaryDto
import app.befos.data.model.MessageDto
import app.befos.data.model.OnboardingRequest
import app.befos.data.model.OptionDto
import app.befos.data.model.ProfileDto
import app.befos.data.model.ProfileUpdateRequest
import app.befos.data.model.ProgressDto
import app.befos.data.model.PublicProfileDto
import app.befos.data.model.QuestionDto
import app.befos.data.model.RecommendationDto
import app.befos.domain.model.CategoryScore
import app.befos.domain.model.Compatibility
import app.befos.domain.model.DiscoveryCard
import app.befos.domain.model.Explanation
import app.befos.domain.model.Interest
import app.befos.domain.model.MatchSummary
import app.befos.domain.model.Message
import app.befos.domain.model.OnboardingData
import app.befos.domain.model.Option
import app.befos.domain.model.Profile
import app.befos.domain.model.ProfileUpdateData
import app.befos.domain.model.PublicProfile
import app.befos.domain.model.Question
import app.befos.domain.model.Recommendation
import app.befos.domain.model.Activity
import app.befos.domain.model.TestProgress

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
)

fun OptionDto.toDomain() = Option(id, text)

fun QuestionDto.toDomain() = Question(
    id = id,
    category = category,
    trait = trait,
    text = text,
    options = options.map { it.toDomain() },
)

fun ProgressDto.toDomain() = TestProgress(answered, total, percent, remaining, completed)

fun CategoryScoreDto.toDomain() = CategoryScore(category, label, score, weight)

fun ExplanationItemDto.toDomain() = Explanation(category, label, text, score)

fun CompatibilityDto.toDomain() = Compatibility(
    overall = overall,
    categories = categories.map { it.toDomain() },
    strengths = strengths.map { it.toDomain() },
    differences = differences.map { it.toDomain() },
    sharedInterests = sharedInterests,
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
