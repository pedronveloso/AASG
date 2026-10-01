package com.pedronveloso.aasg.testkit

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class CaptureOutputPathsTest {
    @Test
    fun inferredPathsMatchSchemaNineConvention() {
        assertEquals("aasg/screenshots/en/store-2-light.png", CaptureOutputPaths.image("store-2", "en", "light"))
        assertEquals("aasg/videos/en/store-2-light.mp4", CaptureOutputPaths.video("store-2", "en", "light"))
        assertEquals("aasg/json/en/store-2-light.json", CaptureOutputPaths.json("store-2", "en", "light"))
        assertEquals(
            "aasg/screenshots/en/store-2-card-light.png",
            CaptureOutputPaths.image("store-2", "en", "light", "card"),
        )
        assertEquals(
            "aasg/videos/en/store-2-light.metadata.json",
            CaptureOutputPaths.metadata(CaptureOutputPaths.video("store-2", "en", "light")),
        )
    }

    @Test
    fun rejectsUnsafePathComponents() {
        assertFailsWith<IllegalArgumentException> {
            CaptureOutputPaths.image("../store-2", "en", "light")
        }
    }
}
