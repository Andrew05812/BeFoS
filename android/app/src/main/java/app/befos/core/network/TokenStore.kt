package app.befos.core.network

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.authDataStore: DataStore<Preferences> by preferencesDataStore(name = "befos_auth")

/** Persisted session tokens. Stored in DataStore (private app storage), never in logs. */
data class StoredAuth(
    val accessToken: String,
    val refreshToken: String,
    val userId: String,
)

class TokenStore(private val context: Context) {

    private object Keys {
        val ACCESS = stringPreferencesKey("access_token")
        val REFRESH = stringPreferencesKey("refresh_token")
        val USER_ID = stringPreferencesKey("user_id")
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

    suspend fun current(): StoredAuth? = auth.first()

    suspend fun save(auth: StoredAuth) {
        context.authDataStore.edit { prefs ->
            prefs[Keys.ACCESS] = auth.accessToken
            prefs[Keys.REFRESH] = auth.refreshToken
            prefs[Keys.USER_ID] = auth.userId
        }
    }

    suspend fun updateTokens(accessToken: String, refreshToken: String) {
        context.authDataStore.edit { prefs ->
            prefs[Keys.ACCESS] = accessToken
            prefs[Keys.REFRESH] = refreshToken
        }
    }

    suspend fun clear() {
        context.authDataStore.edit { it.clear() }
    }
}
