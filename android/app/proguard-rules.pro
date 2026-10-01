# Keep Kotlin serialization metadata and generated serializers.
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**

-keepclassmembers class kotlinx.serialization.json.** {
    *** Companion;
}
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# Keep @Serializable classes' generated serializers for the app package.
-keep,includedescriptorclasses class app.befos.**$$serializer { *; }
-keepclassmembers class app.befos.** {
    *** Companion;
}
-keepclasseswithmembers class app.befos.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# OkHttp / Ktor
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn org.slf4j.**
