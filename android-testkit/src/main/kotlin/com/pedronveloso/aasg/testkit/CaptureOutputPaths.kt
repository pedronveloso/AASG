package com.pedronveloso.aasg.testkit

/** AndroidX Test Storage paths matching AASG's inferred source convention. */
public object CaptureOutputPaths {
    public fun image(
        captureId: String,
        locale: String,
        theme: String,
        artifactId: String? = null,
    ): String = media("screenshots", ".png", captureId, locale, theme, artifactId)

    public fun video(
        captureId: String,
        locale: String,
        theme: String,
        artifactId: String? = null,
    ): String = media("videos", ".mp4", captureId, locale, theme, artifactId)

    public fun json(
        captureId: String,
        locale: String,
        theme: String,
        artifactId: String? = null,
    ): String = media("json", ".json", captureId, locale, theme, artifactId)

    public fun metadata(mediaPath: String): String {
        require(mediaPath.startsWith("aasg/") && '/' in mediaPath && '.' in mediaPath.substringAfterLast('/')) {
            "Expected an AASG media path"
        }
        return mediaPath.substringBeforeLast('.') + ".metadata.json"
    }

    private fun media(
        directory: String,
        extension: String,
        captureId: String,
        locale: String,
        theme: String,
        artifactId: String?,
    ): String {
        listOfNotNull(captureId, locale, theme, artifactId).forEach { value ->
            require(value.matches(Regex("[A-Za-z0-9][A-Za-z0-9._-]*"))) {
                "Capture output path component is invalid: $value"
            }
        }
        val stem = if (artifactId == null) captureId else "$captureId-$artifactId"
        return "aasg/$directory/$locale/$stem-$theme$extension"
    }
}
