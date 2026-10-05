package app.befos.core.network

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.asSharedFlow

private val Context.authDataStore: DataStore<Preferences> by preferencesDataStore(name = "befos_auth")

/** Persisted session tokens. Stored in DataStore (private app storage), never in logs. */
data class StoredAuth(
    val accessToken: String,
    val refreshToken: String,
    val userId: String,
)

/**
 * What the HTTP stack needs from the session: whose token goes on a request, and how a
 * refresh or a sign-out writes the answer back. Declared apart from [TokenStore] because
 * which token leaves the device on which request is exactly the kind of thing that has to
 * be tested, and a DataStore needs an Android Context to exist.
 */
interface SessionTokens {
    suspend fun current(): StoredAuth?

    suspend fun updateTokens(accessToken: String, refreshToken: String)

    suspend fun clear()
}

class TokenStore(private val context: Context) : SessionTokens {

    private val _signedOut = MutableSharedFlow<Unit>(extraBufferCapacity = 1)

    /**
     * Emitted whenever the session tokens disappear, including the case nobody can
     * see from the UI: the access token expired and the refresh was rejected. Without
     * this the user stays on a screen whose only button is «Повторить», which will
     * fail forever, while the error text says «войдите снова».
     */
    val signedOut: SharedFlow<Unit> = _signedOut.asSharedFlow()

    private object Keys {
        val ACCESS = stringPreferencesKey("access_token")
        val REFRESH = stringPreferencesKey("refresh_token")
        val USER_ID = stringPreferencesKey("user_id")
        val EMAIL = stringPreferencesKey("last_email")
    }

    val auth: Flow<StoredAuth?> = context.authDataStore.data.map { prefs ->
        val access = prefs[Keys.ACCESS]
        val refresh = prefs[Keys.REFRESH]
        val userId = prefs[Keys.USER_ID]
        if (access != null && refresh != null && userId != null) {
            StoredAuth(access, refresh, userId)
        } else {
            null
        }
    }

    override suspend fun current(): StoredAuth? = auth.first()

    suspend fun save(auth: StoredAuth, email: String? = null) {
        context.authDataStore.edit { prefs ->
            prefs[Keys.ACCESS] = auth.accessToken
            prefs[Keys.REFRESH] = auth.refreshToken
            prefs[Keys.USER_ID] = auth.userId
            if (email != null) prefs[Keys.EMAIL] = email
        }
    }

    /** Email from the last successful sign-in; survives logout so the auth screen can prefill it. */
    suspend fun lastEmail(): String? = context.authDataStore.data.first()[Keys.EMAIL]

    override suspend fun updateTokens(accessToken: String, refreshToken: String) {
        context.authDataStore.edit { prefs ->
            prefs[Keys.ACCESS] = accessToken
            prefs[Keys.REFRESH] = refreshToken
        }
    }

    override suspend fun clear() {
        context.authDataStore.edit { prefs ->
            prefs.remove(Keys.ACCESS)
            prefs.remove(Keys.REFRESH)
            prefs.remove(Keys.USER_ID)
        }
        _signedOut.emit(Unit)
    }
}
