import java.net.URI
import java.util.Properties
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// Release signing is opt-in: create android/keystore.properties (see
// keystore.properties.example) outside of version control. Without it the
// release variant builds unsigned instead of silently reusing the debug key.
val keystorePropsFile = rootProject.file("keystore.properties")
val keystoreProps = Properties().apply {
    if (keystorePropsFile.exists()) keystorePropsFile.inputStream().use { load(it) }
}

fun envOrProp(name: String, camel: String): String? =
    System.getenv(name) ?: providers.gradleProperty(camel).orNull

val apiBaseUrl = envOrProp("BEFOS_API_BASE_URL", "befos.apiBaseUrl")
val wsBaseUrl = envOrProp("BEFOS_WS_BASE_URL", "befos.wsBaseUrl")
// Local emulator defaults; production backends are served over https/wss.
val debugApiUrl = apiBaseUrl ?: "http://10.0.2.2:8000/"
val debugWsUrl = wsBaseUrl ?: "ws://10.0.2.2:8000/"

// A release artifact is the only build that can reach a real phone, so its backend has to be
// a real host on an encrypted channel. http:// is refused at build time rather than left to
// surface on the device: res/xml/network_security_config.xml permits cleartext only to
// 10.0.2.2, localhost and 127.0.0.1, so a release URL written as http:// would compile,
// install, and then fail every single request with no clue where it went wrong.
val localHosts = setOf("10.0.2.2", "localhost", "127.0.0.1", "::1")

fun requireProductionUrl(name: String, gradleName: String, value: String?, secureScheme: String) {
    val uri = if (value.isNullOrBlank()) null else runCatching { URI(value.trim()) }.getOrNull()
    val host = uri?.host?.lowercase()
    val problem = when {
        value.isNullOrBlank() ->
            "it is not set, and the local emulator default must not ship"
        uri == null -> "\"$value\" is not a valid URI"
        uri?.scheme?.lowercase() != secureScheme ->
            "it must use the $secureScheme:// scheme, not \"${uri?.scheme ?: "no scheme"}\""
        uri?.userInfo != null -> "it must not embed credentials in the URL"
        host.isNullOrEmpty() -> "it must name a host"
        host in localHosts -> "\"$host\" is a machine on someone's desk, not a production backend"
        else -> null
    }
    if (problem != null) {
        throw GradleException(
            "$name is required for release builds: $problem. Set it with the environment " +
                "variable or -P$gradleName=<url> pointing at the deployed backend.",
        )
    }
}

android {
    namespace = "app.befos"
    compileSdk = 35

    defaultConfig {
        applicationId = "app.befos"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        if (keystorePropsFile.exists()) {
            create("release") {
                storeFile = file(keystoreProps.getProperty("storeFile"))
                storePassword = keystoreProps.getProperty("storePassword")
                keyAlias = keystoreProps.getProperty("keyAlias")
                keyPassword = keystoreProps.getProperty("keyPassword")
            }
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            // Backend base URL. For the Android emulator, 10.0.2.2 maps to the host loopback.
            buildConfigField("String", "API_BASE_URL", "\"$debugApiUrl\"")
            buildConfigField("String", "WS_BASE_URL", "\"$debugWsUrl\"")
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            if (keystorePropsFile.exists()) {
                signingConfig = signingConfigs.getByName("release")
            }
            buildConfigField("String", "API_BASE_URL", "\"${apiBaseUrl ?: debugApiUrl}\"")
            buildConfigField("String", "WS_BASE_URL", "\"${wsBaseUrl ?: debugWsUrl}\"")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

// What decides whether a release artifact is being made is the task graph, not the words typed on
// the command line. Matching a substring over the requested task names got both halves wrong, and
// was measured on the previous version of this file: `:app:assemble --dry-run` with no
// BEFOS_API_BASE_URL scheduled `packageRelease` and complained about nothing, so a release APK
// carrying the emulator default built fine; `:app:lintRelease --dry-run` and
// `:app:compileReleaseKotlin --dry-run` — neither produces an artifact — both failed the build.
// The graph names the work that will actually run, including work pulled in by `assemble` and
// `build`, which never say "Release".
//
// The names below are matched exactly, and that is the second measurement: `packageReleaseResources`
// and friends compile the release variant's resources on nearly every release build without ever
// packaging anything, so a `startsWith("packageRelease")` rule made `compileReleaseKotlin` fail
// again. `installRelease` and the signing tasks need no entry here — they depend on packageRelease,
// so it is already in the graph when they run.
val releaseArtifactTasks = setOf("assembleRelease", "bundleRelease", "packageRelease")

gradle.taskGraph.whenReady {
    val shipsRelease = allTasks.any { task ->
        task.project == project && task.name in releaseArtifactTasks
    }
    if (shipsRelease) {
        requireProductionUrl("BEFOS_API_BASE_URL", "befos.apiBaseUrl", apiBaseUrl, "https")
        requireProductionUrl("BEFOS_WS_BASE_URL", "befos.wsBaseUrl", wsBaseUrl, "wss")
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.datastore.preferences)

    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.foundation)
    implementation(libs.compose.animation)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons)

    implementation(libs.ktor.client.core)
    implementation(libs.ktor.client.okhttp)
    implementation(libs.ktor.client.auth)
    implementation(libs.ktor.client.content.negotiation)
    implementation(libs.ktor.client.websockets)
    implementation(libs.ktor.client.logging)
    implementation(libs.ktor.serialization.kotlinx.json)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)

    implementation(libs.coil.compose)

    testImplementation(libs.junit)
    testImplementation(libs.ktor.client.mock)
    testImplementation(libs.mockk)
    testImplementation(libs.turbine)
    testImplementation(libs.kotlinx.coroutines.test)

    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.espresso.core)
    androidTestImplementation(platform(libs.compose.bom))
    androidTestImplementation(libs.compose.ui.test.junit4)

    debugImplementation(libs.compose.ui.tooling)
    debugImplementation(libs.compose.ui.test.manifest)
}
