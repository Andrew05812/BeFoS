package app.befos.data.repository

import app.befos.core.network.ApiResult
import app.befos.core.network.befosJson
import app.befos.core.network.map
import app.befos.data.mapper.toDomain
import app.befos.data.mapper.toRequest
import app.befos.data.remote.ApiService
import app.befos.domain.model.AccountExport
import app.befos.domain.model.ExportSection
import app.befos.domain.model.Interest
import app.befos.domain.model.OnboardingData
import app.befos.domain.model.Profile
import app.befos.domain.model.ProfileUpdateData
import app.befos.domain.model.PublicProfile
import app.befos.domain.repository.ProfileRepository
import java.io.InputStream
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

class ProfileRepositoryImpl(private val api: ApiService) : ProfileRepository {

    override suspend fun me(): ApiResult<Profile> = api.getMe().map { it.toDomain() }

    override suspend fun onboarding(data: OnboardingData): ApiResult<Profile> =
        api.completeOnboarding(data.toRequest()).map { it.toDomain() }

    override suspend fun update(data: ProfileUpdateData): ApiResult<Profile> =
        api.updateProfile(data.toRequest()).map { it.toDomain() }

    override suspend fun uploadPhoto(input: InputStream, contentType: String): ApiResult<Profile> =
        // The picture a person picked is megabytes of it, and `ApiService.uploadPhoto` pulls the
        // whole stream into memory before a byte leaves. View models run their scope on the main
        // thread, so without this shift the file is read through the frame the person is watching.
        withContext(Dispatchers.IO) { api.uploadPhoto(input, contentType).map { it.toDomain() } }

    override suspend fun interests(): ApiResult<List<Interest>> =
        api.getInterests().map { dto -> dto.interests.map { it.toDomain() } }

    // Each of the three answers with the whole profile, as the upload route does, so a screen that
    // removed or moved a photograph paints the row the server holds rather than the row it asked for.
    override suspend fun deletePhoto(photoId: String): ApiResult<Profile> =
        api.deletePhoto(photoId).map { it.toDomain() }

    override suspend fun makePhotoPrimary(photoId: String): ApiResult<Profile> =
        api.makePhotoPrimary(photoId).map { it.toDomain() }

    override suspend fun reorderPhotos(photoIds: List<String>): ApiResult<Profile> =
        api.reorderPhotos(photoIds).map { it.toDomain() }

    override suspend fun publicProfile(userId: String): ApiResult<PublicProfile> =
        api.getPublicProfile(userId).map { it.toDomain() }

    /**
     * Reads the account's own file and names what it holds.
     *
     * The bytes are parsed off the IO dispatcher for the same reason the photograph is read there: a
     * document the size of a life is megabytes, and a view model's scope is the frame the person is
     * watching. A payload that cannot be read answers as a failure rather than as an empty file —
     * see [accountExportOf].
     */
    override suspend fun exportAccount(): ApiResult<AccountExport> =
        withContext(Dispatchers.IO) {
            when (val result = api.exportAccount()) {
                is ApiResult.Success -> {
                    val document = accountExportOf(result.data)
                    if (document == null) {
                        ApiResult.Error(-2, "Не удалось получить данные. Попробуйте ещё раз.")
                    } else {
                        ApiResult.Success(document)
                    }
                }
                is ApiResult.Error -> result
            }
        }
}

/**
 * The file's own numbers, read out of the file.
 *
 * Returns null when the bytes are not the document the door promises: no `counts` object, or a `counts`
 * that names no section. Those are failures, and the difference matters at the screen that offers to
 * save the result — an unreadable payload drawn as «ноль строк» would report an empty account out of a
 * document the client simply did not read, and a person who believed it would walk away from the one
 * copy they had.
 *
 * Nothing here recomputes. The row counts, the ceiling and the names of the cut sections all come from
 * the document, and the byte size is the length of the payload that arrived rather than a re-encoded
 * copy of it — the file the person saves is these exact bytes, so the card has to describe those.
 */
internal fun accountExportOf(bytes: ByteArray): AccountExport? {
    val root = runCatching { befosJson.parseToJsonElement(bytes.toString(Charsets.UTF_8)) }
        .getOrNull() as? JsonObject ?: return null
    val counts = root["counts"] as? JsonObject ?: return null
    val sections = counts.mapNotNull { (name, value) ->
        val rows = (value as? JsonPrimitive)?.intOrNull ?: return@mapNotNull null
        ExportSection(name, rows)
    }
    if (sections.isEmpty()) return null
    val truncated = ((root["limits"] as? JsonObject)?.get("truncated") as? JsonArray)
        ?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
        .orEmpty()
    val generatedAt = (root["generated_at"] as? JsonPrimitive)?.contentOrNull.orEmpty()
    // The day is the server's stamp and nothing else; the header's own name carries the account number,
    // and a file that leaves the phone should not.
    val day = generatedAt.take(10).takeIf { it.matches(Regex("""\d{4}-\d{2}-\d{2}""")) }
    val fileName = if (day == null) "befos-account.json" else "befos-account-$day.json"
    return AccountExport(
        bytes = bytes,
        fileName = fileName,
        generatedAt = generatedAt,
        sections = sections,
        truncated = truncated,
    )
}
