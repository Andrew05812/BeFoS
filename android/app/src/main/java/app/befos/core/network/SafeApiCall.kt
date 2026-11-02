package app.befos.core.network

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.request
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsBytes
import io.ktor.client.statement.bodyAsText
import io.ktor.http.isSuccess
import kotlinx.serialization.Serializable

sealed interface ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>

    /**
     * [code] is the HTTP status, or the negative number this file invents for a failure that never
     * reached the server. [errorCode] is the machine word from the envelope — empty when the response
     * carried none — and it exists because a repair cannot be guessed from a status: 422 covers both
     * «you typed a value we refuse» and «a link we ourselves handed you has aged out», and only the
     * second one is repaired by re-reading the newest page.
     */
    data class Error(val code: Int, val message: String, val errorCode: String = "") : ApiResult<Nothing>
}

inline fun <T, R> ApiResult<T>.map(transform: (T) -> R): ApiResult<R> = when (this) {
    is ApiResult.Success -> ApiResult.Success(transform(data))
    is ApiResult.Error -> this
}

inline fun <T> ApiResult<T>.onSuccess(action: (T) -> Unit): ApiResult<T> {
    if (this is ApiResult.Success) action(data)
    return this
}

fun <T> ApiResult<T>.getOrNull(): T? = (this as? ApiResult.Success)?.data

@Serializable
private data class ErrorDetailDto(
    val code: String = "",
    val message: String = "",
)

@Serializable
private data class ErrorEnvelopeDto(
    val error: ErrorDetailDto? = null,
)

/**
 * A failed response, read as the words the person gets and the code the server meant for a program.
 *
 * The English envelope text never reaches the UI — [localizeBackendError] turns it into product copy —
 * and the envelope's machine code travels beside those words rather than being folded into them. A
 * screen decides what it can *do* by the code: a broken link to the next page is re-read from the
 * newest page, while a rejected input is still the input the person has to fix. Two failures that
 * share a status are not two failures that share a repair.
 */
suspend fun parseError(response: HttpResponse): ApiResult.Error {
    val status = response.status.value
    val (code, message) = try {
        val detail = response.body<ErrorEnvelopeDto>().error
        Pair(detail?.code.orEmpty(), localizeBackendError(detail?.message.orEmpty(), detail?.code.orEmpty(), status))
    } catch (_: Exception) {
        try {
            val text = response.bodyAsText()
            val detail = Regex("\"message\"\\s*:\\s*\"([^\"]+)\"").find(text)?.groupValues?.getOrNull(1).orEmpty()
            val code = Regex("\"code\"\\s*:\\s*\"([^\"]+)\"").find(text)?.groupValues?.getOrNull(1).orEmpty()
            Pair(code, localizeBackendError(detail, code, status))
        } catch (_: Exception) {
            Pair("", defaultHttpMessage(status))
        }
    }
    return ApiResult.Error(status, message, code)
}

/** Never leak raw exception text (English stack-trace messages) into the UI. */
fun friendlyNetworkMessage(e: Throwable): String = when (e) {
    is java.net.SocketTimeoutException -> "Сервер не отвечает. Попробуйте ещё раз."
    is java.net.UnknownHostException -> "Нет подключения к интернету."
    is java.net.ConnectException -> "Сервер недоступен. Проверьте соединение и попробуйте ещё раз."
    is javax.net.ssl.SSLException -> "Защищённое соединение недоступно. Попробуйте ещё раз."
    is io.ktor.client.plugins.HttpRequestTimeoutException -> "Сервер не отвечает. Попробуйте ещё раз."
    else -> defaultHttpMessage(-1)
}

/**
 * Last resort for an unreadable response: the status family in product words, never a bare
 * HTTP code and never a label. Each line names either the cause or what to do, and 403 gets
 * no advice to retry — asking again for something the server already refused is the one
 * suggestion that cannot work.
 */
fun defaultHttpMessage(code: Int): String = when (code) {
    in 500..599 -> "Что-то сломалось с нашей стороны. Попробуйте ещё раз через минуту."
    429 -> "Слишком много запросов. Подождите немного."
    401 -> "Сессия истекла. Войдите снова."
    403 -> "У вашего аккаунта нет доступа к этому."
    404 -> "Этого здесь нет — возможно, анкету или чат удалили."
    in 400..499 -> "Что-то не сходится. Проверьте введённые данные и попробуйте ещё раз."
    -1 -> "Не получилось связаться с сервером. Попробуйте ещё раз."
    else -> "Не удалось выполнить запрос. Попробуйте ещё раз."
}

/**
 * Executes a request and maps the outcome to [ApiResult]. Network failures and
 * non-2xx responses never throw to the caller; they become [ApiResult.Error].
 */
suspend inline fun <reified T> HttpClient.apiCall(
    crossinline block: HttpRequestBuilder.() -> Unit,
): ApiResult<T> {
    val response: HttpResponse = try {
        request(block)
    } catch (e: Exception) {
        return ApiResult.Error(-1, friendlyNetworkMessage(e))
    }
    return if (response.status.isSuccess()) {
        try {
            ApiResult.Success(response.body<T>())
        } catch (e: Exception) {
            ApiResult.Error(-2, "Не удалось получить данные. Попробуйте ещё раз.")
        }
    } else {
        parseError(response)
    }
}

/** Variant for endpoints that return no meaningful body (204 / empty). */
suspend inline fun HttpClient.apiCallUnit(
    crossinline block: HttpRequestBuilder.() -> Unit,
): ApiResult<Unit> {
    val response: HttpResponse = try {
        request(block)
    } catch (e: Exception) {
        return ApiResult.Error(-1, friendlyNetworkMessage(e))
    }
    return if (response.status.isSuccess()) {
        ApiResult.Success(Unit)
    } else {
        parseError(response)
    }
}

/**
 * Variant for a response the client is meant to keep as bytes rather than to fold into a DTO.
 *
 * The account's own file is the case this exists for: it is one document written once, and a screen
 * that showed it as a typed answer would be promising a shape the server never declared. The bytes
 * travel unchanged, and a failure still reads as a failure — an error answer carries bytes of its
 * own, and handing those to a "save" button would be offering somebody their refusal as a file.
 */
suspend inline fun HttpClient.apiCallBytes(
    crossinline block: HttpRequestBuilder.() -> Unit,
): ApiResult<ByteArray> {
    val response: HttpResponse = try {
        request(block)
    } catch (e: Exception) {
        return ApiResult.Error(-1, friendlyNetworkMessage(e))
    }
    return if (response.status.isSuccess()) {
        try {
            ApiResult.Success(response.bodyAsBytes())
        } catch (e: Exception) {
            ApiResult.Error(-2, "Не удалось получить данные. Попробуйте ещё раз.")
        }
    } else {
        parseError(response)
    }
}
